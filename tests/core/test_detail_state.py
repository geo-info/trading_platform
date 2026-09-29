"""Какие лоты ждут деталей — на настоящей Mongo.

Выборка держится на ``$expr`` и на том, что Mongo не считает изменением
``$set`` с прежними значениями, — подделка коллекции ни того ни другого не
умеет. Коллекция временная; без запущенной Mongo тесты пропускаются.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from core.db.mongo.storage import MongoStorage

pytestmark = pytest.mark.mongo

LOT = {"source": "bep", "lot_id": "1", "lot_url": "https://x/lots/view/1/", "status": "Прием заявок"}


async def pending(s: MongoStorage) -> list[str]:
    return [lot["lot_id"] async for lot in s.pending_detail()]


async def test_новый_лот_ждёт_деталей(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    assert await pending(storage) == ["1"]


async def test_после_деталей_лот_не_ждёт(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    await storage.save_detail("1", {"Описание": "дом"}, datetime.now(UTC))
    assert await pending(storage) == []


async def test_тот_же_лот_в_листинге_не_будит_детали(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    await storage.save_detail("1", {"Описание": "дом"}, datetime.now(UTC))
    await storage.upsert(LOT)
    assert await pending(storage) == []


async def test_сменился_статус_детали_перечитываются(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    await storage.save_detail("1", {"Описание": "дом"}, datetime.now(UTC))
    await storage.upsert({**LOT, "status": "Идут торги"})
    assert await pending(storage) == ["1"]


async def test_изменение_во_время_запроса_не_теряется(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    requested = datetime.now(UTC) - timedelta(seconds=1)  # страницу запросили до смены статуса
    await storage.upsert({**LOT, "status": "Идут торги"})
    await storage.save_detail("1", {"Описание": "дом"}, requested)
    assert await pending(storage) == ["1"]


async def test_детали_не_трогают_updated_at_и_не_затираются_листингом(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    before = (await storage.collection.find_one({"lot_id": "1"}))["updated_at"]
    await storage.save_detail("1", {"Описание": "дом"}, datetime.now(UTC))
    await storage.upsert(LOT)
    doc = await storage.collection.find_one({"lot_id": "1"})
    assert doc["updated_at"] == before
    assert doc["detail"] == {"Описание": "дом"}


async def test_свежие_первыми_и_только_своей_площадки(storage: MongoStorage) -> None:
    await storage.upsert(LOT)
    await storage.upsert({**LOT, "lot_id": "2"})
    await storage.upsert({**LOT, "source": "centerr", "lot_id": "3"})
    assert await pending(storage) == ["2", "1"]
