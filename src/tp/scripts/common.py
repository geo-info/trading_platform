"""Общее для скриптов запуска: выбор площадок, параллельный прогон, итоговая таблица.

Площадки выбираются по именам площадок и движков вперемешку:
``kendo atctrade`` — все площадки Kendo и atctrade. Без имён — все.
Площадки идут параллельно (не больше ``PLATFORM_CONCURRENCY``), упавшая не
останавливает остальные: причина — в итоговой таблице, код выхода — не ноль.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass

from collector import Crawler

from core.conf import conf
from tp.btorg.base import Btorg
from tp.btorg.detail import detail_of as btorg_detail
from tp.itender.base import ITender
from tp.itender.detail import detail_of as itender_detail
from tp.kendo.base import Kendo
from tp.kendo.detail import detail_of as kendo_detail
from tp.platforms import platforms
from tp.ruson.base import Ruson
from tp.ruson.detail import detail_of as ruson_detail

#: Движок по имени — для выбора площадок в командной строке.
ENGINES: dict[str, type[Crawler]] = {"itender": ITender, "kendo": Kendo, "btorg": Btorg, "ruson": Ruson}

#: Детальный парсер площадки — по её движку.
DETAIL_OF: dict[type[Crawler], Callable[[type[Crawler]], type[Crawler]]] = {
    ITender: itender_detail,
    Kendo: kendo_detail,
    Btorg: btorg_detail,
    Ruson: ruson_detail,
}


def engine_of(platform: type[Crawler]) -> type[Crawler]:
    return next(engine for engine in ENGINES.values() if issubclass(platform, engine))


def detail_of(platform: type[Crawler]) -> type[Crawler]:
    """Детальный парсер площадки — из пакета её движка."""
    return DETAIL_OF[engine_of(platform)](platform)


def select(names: Sequence[str]) -> list[type[Crawler]]:
    """Площадки по именам площадок и движков; без имён — все. Незнакомое имя — ``ValueError``."""
    known = platforms()
    if not names:
        return list(known.values())
    chosen: dict[str, type[Crawler]] = {}
    unknown = []
    for name in names:
        if name in ENGINES:
            chosen.update(platforms(ENGINES[name]))
        elif name in known:
            chosen[name] = known[name]
        else:
            unknown.append(name)
    if unknown:
        raise ValueError(
            f"нет площадок или движков: {', '.join(unknown)}\n"
            f"движки: {', '.join(ENGINES)}\nплощадки: {', '.join(known)}"
        )
    return list(chosen.values())


@dataclass
class Result:
    """Итог площадки: сколько обработано, сколько нового, ошибки и причина остановки."""

    name: str
    done: int = 0
    new: int = 0
    errors: int = 0
    reason: str = ""
    failure: str = ""
    elapsed: float = 0.0

    @property
    def failed(self) -> bool:
        """Упала — исключение или ошибки при пустом результате: площадка недоступна,
        переехала или сменила разметку, а «0 лотов» не должно выглядеть успехом."""
        return bool(self.failure) or (self.errors > 0 and self.done == 0 and self.new == 0)

    @property
    def why(self) -> str:
        if self.failure:
            return self.failure[:70]
        if self.failed:
            return f"ничего не получено, ошибок {self.errors} ({self.reason})"
        return self.reason


async def run_many(
    chosen: Sequence[type[Crawler]],
    one: Callable[[type[Crawler]], Awaitable[Result]],
    concurrency: int = conf.parsing.platform_concurrency,
) -> list[Result]:
    """``one`` для каждой площадки, не больше ``concurrency`` разом; исключение — в ``failure``."""
    slots = asyncio.Semaphore(concurrency)

    async def guarded(platform: type[Crawler]) -> Result:
        async with slots:
            started = time.monotonic()
            try:
                result = await one(platform)
            except Exception as exc:
                logging.getLogger("tp").exception("[%s] упал", platform.name)
                result = Result(platform.name, failure=f"{type(exc).__name__}: {exc}")
            result.elapsed = time.monotonic() - started
            return result

    return list(await asyncio.gather(*(guarded(p) for p in chosen)))


def report(results: Sequence[Result], done_title: str, new_title: str) -> int:
    """Итоговая таблица; код выхода 1, если какая-то площадка упала."""
    print(f"\n{'площадка':16} {done_title:>8} {new_title:>8} {'ошибок':>7} {'время':>8}  причина")
    for r in sorted(results, key=lambda r: -r.done):
        print(f"{r.name:16} {r.done:>8} {r.new:>8} {r.errors:>7} {r.elapsed:>7.1f}с  {r.why}")
    failed = [r.name for r in results if r.failed]
    print(f"\nвсего {done_title}: {sum(r.done for r in results)}, {new_title}: {sum(r.new for r in results)}")
    print(
        f"площадок: {len(results) - len(failed)} из {len(results)}"
        + (f"; упали: {', '.join(failed)}" if failed else "")
    )
    print(f"хранилище: {conf.mongo.uri}/{conf.mongo.db}.{conf.mongo.collection}")
    return 1 if failed else 0


def parser(description: str) -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument(
        "names", nargs="*", help="площадки и/или движки (itender, kendo, btorg, ruson); без имён — все"
    )
    ap.add_argument("--list", action="store_true", help="показать движки и площадки и выйти")
    ap.add_argument("-v", "--verbose", action="store_true", help="логи фреймворка (каждый запрос)")
    return ap


def setup(args: argparse.Namespace) -> None:
    """Вывод в UTF-8 и логи: свои — всегда, фреймворка — с ``-v``."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("tp").setLevel(logging.INFO)


def print_list() -> None:
    for name, engine in ENGINES.items():
        print(f"{name}: {', '.join(platforms(engine))}")
