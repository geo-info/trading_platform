"""Куда пишет MongoStorage. Без Mongo: клиент подключается лениво, на первом запросе."""

from __future__ import annotations

from core.db.mongo.storage import MongoStorage


async def test_коллекция_по_умолчанию_имя_площадки() -> None:
    s = MongoStorage("bep", uri="mongodb://localhost:1", db_name="trading")
    try:
        assert s.collection.name == "bep"
        assert s.target == "mongodb://localhost:1/trading.bep (source=bep)"
    finally:
        await s.close()


async def test_коллекцию_можно_задать() -> None:
    s = MongoStorage("bep", uri="mongodb://localhost:1", collection="shared")
    try:
        assert s.collection.name == "shared"
    finally:
        await s.close()
