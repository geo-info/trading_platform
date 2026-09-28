"""Детали только актуальных лотов iTender (Fogsoft), до 100 на площадку.

    uv run python -m tp.scripts.itender_detail_active_run                    все площадки
    uv run python -m tp.scripts.itender_detail_active_run alfalot centerr    только эти

Актуальные — по которым ещё можно подать заявку: извещение опубликовано или
идёт приём заявок. Из них, как и в ``tp.scripts.itender_detail_run``, берутся новые
(деталей нет) и изменившиеся после деталей.
"""

from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from datetime import UTC, datetime

from collector import Request

from core.deps import open_run
from tp.itender.base import ITender
from tp.itender.detail import ITenderDetail
from tp.itender.source import PLATFORMS

logger = logging.getLogger(__name__)

#: Статусы как их пишет листинг; «Приём» через «ё» — у tendergarant и utender.
ACTIVE = [
    "Извещение опубликовано",
    "Прием заявок",
    "Приём заявок",
    "Прием заявок на интервале не активен",
    "Приём заявок на интервале не активен",
]


class ActiveDetail(ITenderDetail):
    """Детальный парсер, которому база отдаёт только актуальные лоты."""

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit, ACTIVE)]
        await self.log(f"актуальных ждут деталей: {len(lots)} (не больше {self.params.limit})")
        for lot in lots:
            yield self.request(lot["lot_url"], metadata = {"lot_id": lot["lot_id"]})


def active_detail_of(platform: type[ITender]) -> type[ActiveDetail]:
    """Как ``detail_of``: имя и настройки площадки, модуль — её (для сертификата)."""
    return type(f"{platform.__name__}ActiveDetail", (ActiveDetail, platform), {"__module__": platform.__module__})


async def go(tp: type[ITender]) -> None:
    # До первого запроса: лот, изменённый листингом во время прогона, получит
    # updated_at позже этой отметки и перечитается в следующий раз.
    at = datetime.now(UTC)
    async with open_run(tp.name, active_detail_of(tp)) as run:
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
