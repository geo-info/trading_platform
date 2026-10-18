"""Остаток очереди деталей. Только чтение Mongo, без запросов к площадкам."""

import sys
from collections.abc import Sequence
from datetime import datetime

from pymongo import MongoClient
from pymongo.errors import PyMongoError

from core.conf import conf
from core.db.mongo.queries import pending_detail_query
from tp.scripts.common import parser, print_list, select, setup


def pipeline(source: str) -> list[dict]:
    def count(query: dict) -> list[dict]:
        return [{"$match": query}, {"$count": "n"}]

    return [
        {"$match": {"source": source}},
        {
            "$facet": {
                "total": [{"$count": "n"}],
                "pending": count(pending_detail_query(source)),
                "new": count({"detail_at": {"$exists": False}}),
                "not_found": count({"detail_state": "not_found", "$nor": [pending_detail_query(source)]}),
            }
        },
    ]


def counts(rows: list[dict]) -> dict[str, int]:
    row = rows[0] if rows else {}
    result = {key: (row.get(key) or [{"n": 0}])[0]["n"] for key in ("total", "pending", "new", "not_found")}
    result["stale"] = result["pending"] - result["new"]
    result["checked"] = result["total"] - result["pending"]
    return result


def print_row(name: str, row: dict[str, int]) -> None:
    percent = f"{100 * row['checked'] / row['total']:.1f}%" if row["total"] else "—"
    print(
        f"{name:20} {row['total']:8} {row['checked']:10} {row['not_found']:8} "
        f"{row['new']:10} {row['stale']:10} {row['pending']:10} {percent:>8}"
    )


def main(argv: Sequence[str] | None = None) -> int:
    ap = parser("Сколько лотов осталось проверить детальным парсером (только чтение Mongo).")
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
    print(f"Прогресс деталей на {datetime.now().astimezone():%Y-%m-%d %H:%M:%S %z}; база {conf.mongo.db}")
    print(
        f"{'площадка':20} {'всего':>8} {'проверено':>10} {'нет лота':>8} "
        f"{'впервые':>10} {'повторно':>10} {'осталось':>10} {'готово':>8}"
    )
    total = counts([])
    try:
        with MongoClient(conf.mongo.uri, serverSelectionTimeoutMS=5000) as client:
            for platform in chosen:
                row = counts(list(client[conf.mongo.db][platform.name].aggregate(pipeline(platform.name))))
                print_row(platform.name, row)
                for key in total:
                    total[key] += row[key]
    except PyMongoError as exc:
        print(f"Не удалось получить полный отчёт Mongo: {type(exc).__name__}", file=sys.stderr)
        return 1
    print_row("ИТОГО", total)
    print("Проверено включает отсутствующие лоты. Осталось = впервые + повторно.")
    print("Это число лотов, не HTTP-запросов. Во время сбора очередь может расти;")
    print("площадки посчитаны последовательно, значения меняются по мере записи данных.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
