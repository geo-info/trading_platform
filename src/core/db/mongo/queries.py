"""Общие фильтры очереди для парсера и отчёта о прогрессе."""


def pending_detail_query(source: str) -> dict:
    return {
        "source": source,
        "$or": [
            {"detail_at": {"$exists": False}},
            {"$expr": {"$gt": [{"$ifNull": ["$listing_changed_at", "$updated_at"]}, "$detail_at"]}},
        ],
    }
