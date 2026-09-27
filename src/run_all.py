"""Обход всех площадок разом.

    uv run python -m run_all                  все площадки
    uv run python -m run_all centerr etb      только названные
    uv run python -m run_all --max-pages 2    короткий прогон
    uv run python -m run_all --since 2026-01-01  окно по дате
    uv run python -m run_all --list           что вообще есть

Площадки обходятся **параллельно**, и это тот случай, когда параллелизм
оправдан: серверы разные, друг другу они не мешают. Внутри одной площадки
конкуренция, наоборот, бесполезна — упор там в пропускную способность самого
сайта, поэтому ``concurrency`` у парсеров остаётся единицей.

Падение одной площадки не трогает остальные: исключение попадает в её строку
итоговой таблицы вместе с тем, что она успела, а соседи досчитываются до
конца. Разводит площадки ``crawl_many`` фреймворка; здесь — куда идут лоты и
что видит человек.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import pkgutil
import sys
import time
from dataclasses import dataclass, field
from datetime import date
from importlib import import_module
from typing import Any

from collector import Crawl, Outcome, Stats, crawl_many
from pymongo import AsyncMongoClient

from core.db import MongoStore
from core.db.mongo_store import new_run_id
from core.settings import settings as config
from tp import platform as platform_pkg
from tp.base import TenderFogsoft

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Platform:
    key: str
    parser_cls: type[TenderFogsoft]
    module: Any


@dataclass(slots=True)
class Result:
    key: str
    #: Что обход сделал — как его считает фреймворк: лоты, запросы, ошибки,
    #: повторы (запросы, которые обход уже ставил в очередь) и причина конца.
    #: Пустая причина — площадка упала, не начав обход.
    stats: Stats = field(default_factory=lambda: Stats(reason=""))
    #: Что с лотами стало здесь, в consume.
    new: int = 0
    updated: int = 0
    #: Лоты с ``validation.ok = false``: записаны, но сверки не сошлись.
    invalid: int = 0
    #: Лоты с подписями вне реестра: площадка добавила или переименовала поле.
    unknown: int = 0
    elapsed: float = 0.0
    failure: str = ""

    @property
    def ok(self) -> bool:
        """Площадка дошла до конца. Прерванная — не дошла, хоть и без ошибки."""
        return not self.failure and self.stats.reason != "cancelled"

    @property
    def mark(self) -> str:
        if self.failure:
            return "ОШИБКА"
        return "ПРЕРВАНО" if self.stats.reason == "cancelled" else "ГОТОВО"


def finish(result: Result, outcome: Outcome) -> Result:
    """Дописать в итог площадки то, чем закончился её обход.

    Статистика берётся и у упавшей площадки: площадка, упавшая после двух
    тысяч лотов, так и говорит об этом, а не показывает прочерки.
    """
    if outcome.crawl is not None:
        result.stats = outcome.crawl.stats
    if outcome.error is not None:
        result.failure = f"{type(outcome.error).__name__}: {outcome.error}"
    result.elapsed = outcome.elapsed
    return result


def discover() -> list[Platform]:
    """Площадки — это модули пакета ``tp.platform``, по одной на модуль.

    Модуль, который не дотягивает до контракта, не пропускается молча, а
    роняет запуск со списком нарушений: «почему мой парсер не виден» — худший
    жанр отладки, и обмен его на явную ошибку при импорте выгоден.
    """
    found: list[Platform] = []
    broken: list[str] = []

    for info in sorted(pkgutil.iter_modules(platform_pkg.__path__), key=lambda i: i.name):
        # Подпакеты — не площадки по определению.
        if info.ispkg:
            continue

        module = import_module(f"{platform_pkg.__name__}.{info.name}")
        classes = [
            value
            for value in vars(module).values()
            if isinstance(value, type) and issubclass(value, TenderFogsoft) and value is not TenderFogsoft
        ]
        named = [cls for cls in classes if getattr(cls, "name", None)]

        if len(named) != 1:
            broken.append(f"{info.name}: классов TenderFogsoft с именем — {len(named)}, нужен ровно один")
            continue

        found.append(Platform(key=named[0].name, parser_cls=named[0], module=module))

    if broken:
        raise RuntimeError(
            "Модули в tp.platform не соответствуют контракту (ровно один наследник "
            "TenderFogsoft с непустым name):\n  " + "\n  ".join(broken)
        )
    return found


async def run(platforms: list[Platform], params: dict[str, Any], quiet: bool) -> list[Result]:
    """Запустить площадки разом через ``crawl_many``, печатая ход по мере поступления.

    Сколько площадок идёт разом, чья строка лога и падение одной без остальных —
    это делает фреймворк. Здесь — что делать с лотами (``consume``: в Mongo, с
    подсчётом новых и обновлённых) и что показать человеку.

    Клиент Mongo один на весь запуск: у него внутри свой пул соединений, и
    шестнадцать отдельных клиентов — это шестнадцать пулов и шестнадцать
    наборов фоновых задач мониторинга там, где хватает одного набора.
    """
    clock = time.monotonic()
    # Одна метка на весь запуск: «что видел последний обход» — один запрос.
    run_id = new_run_id()
    results = {p.key: Result(key=p.key) for p in platforms}

    async def consume(crawl: Crawl) -> None:
        result = results[crawl.crawler.name]
        async with MongoStore(result.key, client=client, run_id=run_id) as store:
            async for item in crawl.stream():
                result.invalid += not item["validation"]["ok"]
                result.unknown += bool(item["validation"]["unknown_labels"])
                if await store.upsert(item):
                    result.new += 1
                else:
                    result.updated += 1

    async def log(name: str, message: str) -> None:
        # Метка обязательна: шестнадцать обходов пишут в один поток вперемешку.
        # Секунды от общего старта заодно показывают, что площадки идут разом.
        if not quiet:
            print(f"[{time.monotonic() - clock:6.1f}с] {name:15} {message}", flush=True)

    client: AsyncMongoClient = AsyncMongoClient(config.mongo_uri)
    try:
        print(
            f"запущено площадок: {len(platforms)}, одновременно до {config.platform_concurrency}, "
            f"run_id {run_id}\n",
            flush=True,
        )
        finished = 0
        async for outcome in crawl_many(
            [p.parser_cls for p in platforms],
            concurrency=config.platform_concurrency,
            params=params,
            consume=consume,
            log=log,
        ):
            result = finish(results[outcome.crawler_cls.name], outcome)
            finished += 1
            detail = (
                f"лотов {result.stats.items}, новых {result.new}, невалидных {result.invalid}, "
                f"с незнакомыми подписями {result.unknown}, запросов {result.stats.requests}"
            )
            if result.failure:
                logger.warning("площадка %s упала: %s", result.key, result.failure)
                detail += f" — {result.failure[:60]}"
            print(
                f"[{time.monotonic() - clock:6.1f}с] {result.key:15} {result.mark} "
                f"({finished}/{len(platforms)}) за {result.elapsed:.1f}с  {detail}",
                flush=True,
            )
        return list(results.values())
    finally:
        await client.close()


def report(results: list[Result]) -> int:
    """Итоговая таблица. Возвращает код выхода: не ноль, если кто-то не дошёл до конца."""
    results.sort(key=lambda r: (not r.ok, -r.stats.items))
    width = max(len(r.key) for r in results)

    print(
        f"\n{'площадка':{width}}  {'лотов':>6} {'новых':>6} {'обнов':>6} {'невал':>6} {'незн':>5} "
        f"{'запр':>5} {'повт':>5} {'ош':>3}  {'время':>7}  причина"
    )
    for r in results:
        # Статистика печатается и у упавшей площадки: сколько она успела.
        s = r.stats
        why = f"{s.reason} — {r.failure[:44]}" if r.failure else s.reason
        print(
            f"{r.key:{width}}  {s.items:>6} {r.new:>6} {r.updated:>6} {r.invalid:>6} {r.unknown:>5} "
            f"{s.requests:>5} {s.duplicates:>5} {s.errors:>3}  {r.elapsed:6.1f}с  {why}"
        )

    failed = [r for r in results if not r.ok]
    print(
        f"\nитого: лотов {sum(r.stats.items for r in results)}, новых {sum(r.new for r in results)}, "
        f"невалидных {sum(r.invalid for r in results)}, "
        f"с незнакомыми подписями {sum(r.unknown for r in results)}, "
        f"запросов {sum(r.stats.requests for r in results)}, "
        f"повторных не отправлено {sum(r.stats.duplicates for r in results)}, "
        f"площадок {len(results) - len(failed)} из {len(results)}"
    )
    print(f"хранилище: {config.mongo_uri}/{config.mongo_db}.{config.mongo_collection}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description="Обход всех площадок разом.")
    ap.add_argument("keys", nargs="*", help="какие площадки обойти; по умолчанию все")
    ap.add_argument("--max-pages", type=int, metavar="N", help="предел страниц листинга на площадку")
    ap.add_argument(
        "--since",
        type=date.fromisoformat,
        metavar="ГГГГ-ММ-ДД",
        help="листать, пока на странице есть лот с приёмом заявок не раньше этой даты",
    )
    ap.add_argument(
        "--max-errors",
        type=int,
        metavar="N",
        help="сколько упавших запросов площадка переживает в этом прогоне",
    )
    ap.add_argument("--list", action="store_true", help="показать список площадок и выйти")
    ap.add_argument("-v", "--verbose", action="store_true", help="добавить логи самого фреймворка")
    ap.add_argument("-q", "--quiet", action="store_true", help="только итоговая таблица")
    return ap


def run_params(args: argparse.Namespace) -> dict[str, Any]:
    """Параметры прогона для фреймворка — только те, что заданы.

    Незаданный ключ оставляет умолчание площадки: передать его как ``None``
    значило бы «без окна» или «без предела» вместо «как настроено».
    """
    given = {"max_pages": args.max_pages, "since": args.since, "max_errors": args.max_errors}
    return {name: value for name, value in given.items() if value is not None}


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)

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
        if unknown := [k for k in args.keys if k not in known]:
            print(f"Неизвестные площадки: {', '.join(unknown)}", file=sys.stderr)
            print(f"Известные: {', '.join(sorted(known))}", file=sys.stderr)
            return 2
        platforms = [p for p in platforms if p.key in set(args.keys)]

    started = time.monotonic()
    results = asyncio.run(run(platforms, run_params(args), quiet=args.quiet))
    code = report(results)
    print(f"всего заняло {time.monotonic() - started:.1f}с")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
