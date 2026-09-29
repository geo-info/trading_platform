"""Детали лотов: новые и изменившиеся — со страниц лотов (торгов) в Mongo.

Какие лоты обходить, решает база (``pending_detail``): деталей ещё нет или
лот изменился после них. Сначала — свежие.

    uv run python -m tp.scripts.detail                   все площадки, до 100 лотов на каждую
    uv run python -m tp.scripts.detail rus_on --limit 500
    uv run python -m tp.scripts.detail itender
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence
from datetime import UTC, datetime

from collector import Crawler

from core.deps import open_run
from tp.scripts.common import Result, detail_of, parser, print_list, report, run_many, select, setup

LIMIT = 100


async def fetch_details(platform: type[Crawler], limit: int) -> Result:
    """Детали до ``limit`` лотов площадки; ``detail=None`` — лота на странице уже нет."""
    # До первого запроса: лот, изменённый листингом во время прогона, получит
    # updated_at позже этой отметки и перечитается в следующий раз.
    at = datetime.now(UTC)
    async with open_run(detail_of(platform), params={"limit": limit}) as run:
        done = gone = 0
        async for item in run.crawl.stream():
            await run.storage.save_detail(item["lot_id"], item["detail"], at)
            done += 1
            gone += item["detail"] is None
        stats = run.crawl.stats
        await run.log(
            f"готово: деталей {done}, лотов нет на странице {gone}, ошибок {stats.errors} ({stats.reason})"
        )
        return Result(platform.name, done=done - gone, new=gone, errors=stats.errors, reason=stats.reason)


def main(argv: Sequence[str] | None = None) -> int:
    ap = parser("Детали лотов, ждущих их в базе: новых и изменившихся.")
    ap.add_argument(
        "--limit",
        type=int,
        default=LIMIT,
        metavar="N",
        help=f"лотов на площадку за прогон (по умолчанию {LIMIT})",
    )
    args = ap.parse_args(argv)
    setup(args)
    if args.list:
        print_list()
        return 0
    try:
        chosen = select(args.names)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    print(f"площадок {len(chosen)}, до {args.limit} лотов на каждую\n", flush=True)
    results = asyncio.run(run_many(chosen, lambda p: fetch_details(p, args.limit)))
    return report(results, "деталей", "снято")


if __name__ == "__main__":
    raise SystemExit(main())
