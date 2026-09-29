"""MongoStorage на настоящей Mongo: upsert, updated_at, save_detail, count, индекс.

Какие лоты ждут деталей — в test_detail_state.py.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pymongo.errors import DuplicateKeyError

from core.db.mongo.storage import MongoStorage

pytestmark = pytest.mark.mongo

LOT = {"source": "bep", "lot_id": "1", "lot_url": "https://x/lots/1", "status": "Прием заявок"}


async def doc(s: MongoStorage, lot_id: str = "1") -> dict:
    return await s.collection.find_one({"lot_id": lot_id})


async def test_upsert_новый_true_повтор_false(storage: MongoStorage) -> None:
    assert await storage.upsert(LOT) is True
    assert await storage.upsert(LOT) is False
    assert await storage.count() == 1


async def test_updated_at_сдвигается_только_при_изменении(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    first = await doc(storage)
    assert first["created_at"] == first["updated_at"]
    await storage.upsert(LOT)
    assert (await doc(storage))["updated_at"] == first["updated_at"]
    await storage.upsert({**LOT, "status": "Идут торги"})
    changed = await doc(storage)
    assert changed["updated_at"] > first["updated_at"]
    assert changed["created_at"] == first["created_at"]


async def test_upsert_без_ключа_ошибка(storage: MongoStorage) -> None:
    with pytest.raises(ValueError, match="lot_id"):
        await storage.upsert({"source": "bep", "lot_url": "u"})


async def test_уникальный_индекс_по_source_и_lot_id(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    with pytest.raises(DuplicateKeyError):
        await storage.collection.insert_one({"source": "bep", "lot_id": "1"})


async def test_pending_detail_отдаёт_trade_url(storage: MongoStorage) -> None:
    await storage.upsert({**LOT, "trade_url": "https://x/trade/1"})
    await storage.upsert({**LOT, "lot_id": "2"})
    got = {lot["lot_id"]: lot async for lot in storage.pending_detail()}
    assert got["1"] == {"lot_id": "1", "lot_url": "https://x/lots/1", "trade_url": "https://x/trade/1"}
    assert got["2"] == {"lot_id": "2", "lot_url": "https://x/lots/1"}


async def test_pending_detail_limit(storage: MongoStorage) -> None:
    for i in range(5):
        await storage.upsert({**LOT, "lot_id": str(i)})
    assert len([lot async for lot in storage.pending_detail(limit=2)]) == 2


async def test_save_detail_пишет_детали_и_время(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    at = datetime.now(UTC)
    await storage.save_detail("1", {"Описание": "дом"}, at)
    d = await doc(storage)
    assert d["detail"] == {"Описание": "дом"}
    assert abs((d["detail_at"].replace(tzinfo=UTC) - at).total_seconds()) < 0.01


async def test_save_detail_none_только_время_детали_целы(storage: MongoStorage) -> None:
    """Лот сняли с торгов: страницу смотрели, лота нет — прежние детали остаются."""
    await storage.upsert(LOT)
    await storage.save_detail("1", {"Описание": "дом"}, datetime.now(UTC))
    await storage.upsert({**LOT, "status": "Идут торги"})
    assert [lot["lot_id"] async for lot in storage.pending_detail()] == ["1"]
    await storage.save_detail("1", None, datetime.now(UTC))
    assert (await doc(storage))["detail"] == {"Описание": "дом"}
    assert [lot async for lot in storage.pending_detail()] == []


async def test_save_detail_none_без_прежних_деталей(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    await storage.save_detail("1", None, datetime.now(UTC))
    d = await doc(storage)
    assert "detail" not in d
    assert "detail_at" in d
    assert [lot async for lot in storage.pending_detail()] == []


async def test_count_только_своя_площадка(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    await storage.upsert({**LOT, "source": "centerr"})
    assert await storage.count() == 1
