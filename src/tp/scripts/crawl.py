"""Обход листингов: лоты площадок — в Mongo.

uv run python -m tp.scripts.crawl                    все площадки, до 30 страниц
uv run python -m tp.scripts.crawl kendo atctrade     движок и отдельная площадка
uv run python -m tp.scripts.crawl --max-pages 5
uv run python -m tp.scripts.crawl --list
"""

from __future__ import annotations

import asyncio
import sys
from collections.abc import Sequence

from collector import Crawler

from core.deps import open_run
from tp.scripts.common import Result, parser, print_list, report, run_many, select, setup

MAX_PAGES = 30


async def crawl(platform: type[Crawler], max_pages: int) -> Result:
    """Листинг площадки до ``max_pages`` страниц; каждый лот — upsert."""
    async with open_run(platform, params={"max_pages": max_pages}) as run:
        done = new = 0
        async for item in run.crawl.stream():
            done += 1
            new += await run.storage.upsert(item)
        stats = run.crawl.stats
        await run.log(f"готово: лотов {done}, новых {new}, ошибок {stats.errors} ({stats.reason})")
        return Result(platform.name, done=done, new=new, errors=stats.errors, reason=stats.reason)


def main(argv: Sequence[str] | None = None) -> int:
    ap = parser("Обход листингов площадок: лоты — в Mongo.")
    ap.add_argument(
        "--max-pages",
        type=int,
        default=MAX_PAGES,
        metavar="N",
        help=f"страниц листинга на площадку (по умолчанию {MAX_PAGES})",
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
    print(f"площадок {len(chosen)}, до {args.max_pages} страниц листинга на каждую\n", flush=True)
    results = asyncio.run(run_many(chosen, lambda p: crawl(p, args.max_pages)))
    return report(results, "лотов", "новых")


if __name__ == "__main__":
    raise SystemExit(main())
