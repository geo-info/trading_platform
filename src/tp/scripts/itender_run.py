"""Прогон площадок iTender (Fogsoft).

    uv run python -m tp.scripts.itender_run                    все площадки
    uv run python -m tp.scripts.itender_run alfalot centerr    только эти
"""

from __future__ import annotations

import asyncio
import logging
import sys

from core.deps import open_run
from tp.itender.base import ITender
from tp.platforms import platforms

logger = logging.getLogger(__name__)

PLATFORMS = platforms(ITender)


async def go(tp: type[ITender]) -> None:
    async with open_run(tp.name, tp) as run:
        await run.log(f"пишем в {run.storage.target}")
        new = sum([await run.storage.upsert(item) async for item in run.crawl.stream()])

        s, total = run.crawl.stats, await run.storage.count()
        await run.log(f"готово: лотов {s.items}, новых {new}, в базе {total}, ошибок {s.errors} ({s.reason})")


async def go_many(names: list[str], limit: int = 16) -> None:
    if unknown := [name for name in names if name not in PLATFORMS]:
        raise SystemExit(f"нет площадок {unknown}; есть: {', '.join(PLATFORMS)}")

    platforms = [PLATFORMS[name] for name in names] if names else list(PLATFORMS.values())
    slots = asyncio.Semaphore(limit)

    async def one(tp: type[ITender]) -> None:
        async with slots:
            await go(tp)

    # Упавшая площадка не прерывает остальные: ошибки — списком в конце.
    results = await asyncio.gather(*(one(tp) for tp in platforms), return_exceptions = True)
    for tp, result in zip(platforms, results):
        if isinstance(result, Exception):
            logger.error("[%s] упал: %r", tp.name, result.__cause__ or result)


def main() -> None:
    logging.basicConfig(level = logging.INFO, format = "%(asctime)s %(levelname)s %(message)s")
    asyncio.run(go_many(sys.argv[1:]))


if __name__ == '__main__':
    main()
