"""Сколько лотов iTender ещё ждут деталей — только чтение базы.

    uv run python -m tp.scripts.itender_detail_stat                    все площадки
    uv run python -m tp.scripts.itender_detail_stat alfalot centerr    только эти

Колонки: всего лотов; с деталями; без деталей — новые, страницу ещё не
открывали; устарели — лот изменился на площадке после деталей. Ждут =
без деталей + устарели, их и берёт ``tp.scripts.itender_detail_run``.
"""

from __future__ import annotations

import asyncio
import sys

from core.conf import conf
from core.db.mongo.client import create_client
from tp.itender.source import PLATFORMS

NO_DETAIL = {"detail_at": {"$exists": False}}
STALE = {"detail_at": {"$exists": True}, "$expr": {"$gt": ["$updated_at", "$detail_at"]}}


async def stat(names: list[str], statuses: list[str] | None = None) -> None:
    """Таблица по площадкам; ``statuses`` — считать только лоты с этими статусами."""
    if unknown := [name for name in names if name not in PLATFORMS]:
        raise SystemExit(f"нет площадок {unknown}; есть: {', '.join(PLATFORMS)}")

    client = create_client()
    db = client[conf.mongo.db]
    header = f"{'площадка':<16}{'всего':>8}{'с деталями':>12}{'без деталей':>13}{'устарели':>10}{'ждут':>8}"
    print(header, "-" * len(header), sep = "\n")
    totals = [0] * 5
    try:
        for name in names or PLATFORMS:
            # Каждая площадка — в своей коллекции, как пишет tp.scripts.itender_run.
            lots = db[name]
            query: dict = {"source": name}
            if statuses:
                query["status"] = {"$in": statuses}
            total = await lots.count_documents(query)
            no_detail = await lots.count_documents({**query, **NO_DETAIL})
            stale = await lots.count_documents({**query, **STALE})
            row = [total, total - no_detail, no_detail, stale, no_detail + stale]
            totals = [a + b for a, b in zip(totals, row)]
            print(f"{name:<16}{row[0]:>8}{row[1]:>12}{row[2]:>13}{row[3]:>10}{row[4]:>8}")
    finally:
        await client.close()
    print("-" * len(header))
    print(f"{'итого':<16}{totals[0]:>8}{totals[1]:>12}{totals[2]:>13}{totals[3]:>10}{totals[4]:>8}")


def main() -> None:
    asyncio.run(stat(sys.argv[1:]))


if __name__ == '__main__':
    main()
