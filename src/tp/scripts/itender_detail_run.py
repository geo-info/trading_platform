"""Детали лотов iTender (Fogsoft): новые и изменившиеся, до 100 на площадку.

    uv run python -m tp.scripts.itender_detail_run                    все площадки
    uv run python -m tp.scripts.itender_detail_run alfalot centerr    только эти
"""

from __future__ import annotations

import asyncio
import logging
import sys
from datetime import UTC, datetime

from core.deps import open_run
from tp.itender.base import ITender
from tp.itender.detail import detail_of
from tp.itender.source import PLATFORMS

logger = logging.getLogger(__name__)


async def go(tp: type[ITender]) -> None:
    # До первого запроса: лот, изменённый листингом во время прогона, получит
    # updated_at позже этой отметки и перечитается в следующий раз.
    at = datetime.now(UTC)
    async with open_run(tp.name, detail_of(tp)) as run:
        done = 0
        async for item in run.crawl.stream():
            await run.storage.save_detail(item["lot_id"], item["detail"], at)
            done += 1

        s = run.crawl.stats
        await run.log(f"готово: деталей {done}, ошибок {s.errors} ({s.reason})")


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
