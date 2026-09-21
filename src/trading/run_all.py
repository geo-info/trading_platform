"""Обход всех площадок разом.

    uv run python -m trading.run_all                  все площадки
    uv run python -m trading.run_all centerr etb      только названные
    uv run python -m trading.run_all --max-pages 2    короткий прогон
    uv run python -m trading.run_all --list           что вообще есть

Площадки обходятся **параллельно**, и это тот случай, когда параллелизм
оправдан: серверы разные, друг другу они не мешают. Внутри одной площадки
конкуренция, наоборот, бесполезна — упор там в пропускную способность самого
сайта, поэтому ``concurrency`` у парсеров остаётся единицей.

Падение одной площадки не трогает остальные: исключение попадает в её строку
итоговой таблицы, а соседи досчитываются до конца.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import pkgutil
import sys
import time
from dataclasses import dataclass
from importlib import import_module
from types import ModuleType
from typing import Any

from collector import Parser, open_crawler

from trading import parsers as parsers_pkg
from trading.storage import TinyDbStore

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Platform:
    """Модуль площадки, проверенный на пригодность к запуску."""

    key: str
    parser_cls: type[Parser]
    module: ModuleType

    @property
    def db_path(self) -> Any:
        return self.module.DB_PATH


@dataclass(slots=True)
class Result:
    key: str
    items: int = 0
    new: int = 0
    updated: int = 0
    requests: int = 0
    errors: int = 0
    reason: str = ""
    elapsed: float = 0.0
    failure: str = ""


def discover() -> list[Platform]:
    """Все модули ``trading.parsers``, у которых есть всё нужное для запуска.

    Модуль, который не дотягивает до контракта, не пропускается молча, а
    роняет запуск с внятным сообщением: «почему мой парсер не виден» — худший
    жанр отладки, и обмен его на явную ошибку при импорте выгоден.
    """
    found: list[Platform] = []
    broken: list[str] = []

    for info in sorted(pkgutil.iter_modules(parsers_pkg.__path__), key=lambda i: i.name):
        module = import_module(f"{parsers_pkg.__name__}.{info.name}")
        source = getattr(module, "SOURCE", None)
        classes = [
            value
            for value in vars(module).values()
            if isinstance(value, type) and issubclass(value, Parser) and value is not Parser
        ]
        own = [cls for cls in classes if getattr(cls, "name", None) == source]

        if source is None or not hasattr(module, "DB_PATH") or len(own) != 1:
            broken.append(
                f"{info.name}: SOURCE={source!r}, DB_PATH={'есть' if hasattr(module, 'DB_PATH') else 'нет'}, "
                f"классов с name == SOURCE: {len(own)}"
            )
            continue

        found.append(Platform(key=source, parser_cls=own[0], module=module))

    if broken:
        raise RuntimeError(
            "Модули в trading.parsers не соответствуют контракту "
            "(нужны SOURCE, DB_PATH и ровно один Parser с name == SOURCE):\n  " + "\n  ".join(broken)
        )
    return found


def make_log(key: str, clock: float, quiet: bool) -> Any:
    """Шов ``log=`` для одного краула: помечает строку площадкой и временем.

    Метка обязательна: шестнадцать обходов пишут в один поток вперемешку, и
    без неё строки нечитаемы. Секунды от общего старта заодно показывают, что
    площадки идут разом, а не по очереди, — иначе это видно только по итогу.
    """

    async def log(message: str) -> None:
        if not quiet:
            print(f"[{time.monotonic() - clock:6.1f}с] {key:15} {message}", flush=True)

    return log


async def crawl_one(platform: Platform, params: dict[str, str], clock: float, quiet: bool) -> Result:
    """Обойти одну площадку, складывая лоты в её собственное хранилище."""
    result = Result(key=platform.key)
    started = time.monotonic()
    log = make_log(platform.key, clock, quiet)
    try:
        with TinyDbStore(platform.db_path) as store:
            async with open_crawler(platform.parser_cls, params=params, log=log) as crawler:
                async for item in crawler.stream():
                    if store.upsert(item):
                        result.new += 1
                    else:
                        result.updated += 1
        stats = crawler.stats
        result.items, result.requests = stats.items, stats.requests
        result.errors, result.reason = stats.errors, stats.reason
    except Exception as exc:  # noqa: BLE001 — падение площадки не должно ронять остальные
        result.failure = f"{type(exc).__name__}: {exc}"
        logger.warning("площадка %s упала: %s", platform.key, result.failure)
    result.elapsed = time.monotonic() - started
    return result


async def run(platforms: list[Platform], params: dict[str, str], quiet: bool) -> list[Result]:
    """Запустить все площадки разом, печатая ход обхода по мере поступления."""
    clock = time.monotonic()
    tasks = [asyncio.create_task(crawl_one(p, params, clock, quiet), name=p.key) for p in platforms]
    print(f"запущено площадок разом: {len(tasks)} — {', '.join(p.key for p in platforms)}\n", flush=True)

    results: list[Result] = []
    for finished in asyncio.as_completed(tasks):
        result = await finished
        results.append(result)
        mark = "ОШИБКА" if result.failure else "ГОТОВО"
        detail = (
            result.failure[:60]
            if result.failure
            else (f"лотов {result.items}, новых {result.new}, запросов {result.requests}")
        )
        print(
            f"[{time.monotonic() - clock:6.1f}с] {result.key:15} {mark} "
            f"({len(results)}/{len(tasks)}) за {result.elapsed:.1f}с  {detail}",
            flush=True,
        )
    return results


def report(results: list[Result]) -> int:
    """Итоговая таблица. Возвращает код выхода: не ноль, если кто-то упал."""
    results.sort(key=lambda r: (bool(r.failure), -r.items))
    width = max(len(r.key) for r in results)

    print(
        f"\n{'площадка':{width}}  {'лотов':>6} {'новых':>6} {'обнов':>6} {'запр':>5} {'ош':>3}  {'время':>7}  причина"
    )
    for r in results:
        if r.failure:
            print(
                f"{r.key:{width}}  {'—':>6} {'—':>6} {'—':>6} {'—':>5} {'—':>3}  {r.elapsed:6.1f}с  {r.failure[:44]}"
            )
        else:
            print(
                f"{r.key:{width}}  {r.items:>6} {r.new:>6} {r.updated:>6} {r.requests:>5} {r.errors:>3}  "
                f"{r.elapsed:6.1f}с  {r.reason}"
            )

    failed = [r for r in results if r.failure]
    total = sum(r.items for r in results)
    print(
        f"\nитого: лотов {total}, новых {sum(r.new for r in results)}, "
        f"запросов {sum(r.requests for r in results)}, "
        f"площадок {len(results) - len(failed)} из {len(results)}"
    )
    return 1 if failed else 0


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    ap = argparse.ArgumentParser(description="Обход всех площадок разом.")
    ap.add_argument("keys", nargs="*", help="какие площадки обойти; по умолчанию все")
    ap.add_argument("--max-pages", type=int, metavar="N", help="предел страниц листинга на площадку")
    ap.add_argument("--list", action="store_true", help="показать список площадок и выйти")
    ap.add_argument("-v", "--verbose", action="store_true", help="добавить логи самого фреймворка")
    ap.add_argument("-q", "--quiet", action="store_true", help="только итоговая таблица")
    args = ap.parse_args(argv)

    # Строки парсеров идут через шов log= с меткой площадки. Логи фреймворка
    # (каждый запрос и ответ) метки не несут и при шестнадцати обходах сразу
    # превращаются в кашу, поэтому они отдельно, под -v.
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    platforms = discover()
    if args.list:
        for p in platforms:
            print(f"  {p.key:15} {p.parser_cls.start_urls[0]}")
        return 0

    if args.keys:
        known = {p.key for p in platforms}
        unknown = [k for k in args.keys if k not in known]
        if unknown:
            print(f"Неизвестные площадки: {', '.join(unknown)}", file=sys.stderr)
            print(f"Известные: {', '.join(sorted(known))}", file=sys.stderr)
            return 2
        platforms = [p for p in platforms if p.key in set(args.keys)]

    if args.max_pages is not None:
        # MAX_PAGES живёт в модуле площадки, и parse() читает его при каждом
        # вызове — подмена здесь действует на весь запуск.
        for p in platforms:
            p.module.MAX_PAGES = args.max_pages

    started = time.monotonic()
    results = asyncio.run(run(platforms, params={}, quiet=args.quiet))
    code = report(results)
    print(f"всего заняло {time.monotonic() - started:.1f}с")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
