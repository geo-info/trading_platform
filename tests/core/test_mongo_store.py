"""Проверки ``MongoStore`` на подделке коллекции."""

from __future__ import annotations

import pytest

from core.db import MongoStore
from core.db.mongo import client as client_module
from core.db.mongo import create_client
from core.db.mongo import storage as storage_module
from core.conf import conf
from tests.core.fake_mongo import FakeClient

LOT = {"source": "bep", "lot_id": "1", "price": "100,00"}


def store(client: FakeClient, source: str = "bep") -> MongoStore:
    return MongoStore(source, client=client)


async def test_upsert_различает_вставку_и_обновление() -> None:
    client = FakeClient()
    async with store(client) as s:
        assert await s.upsert(LOT) is True
        assert await s.upsert(LOT) is False
        assert await s.upsert({**LOT, "lot_id": "2"}) is True


async def test_upsert_обновляет_поля_прежнего_документа() -> None:
    client = FakeClient()
    async with store(client) as s:
        await s.upsert(LOT)
        await s.upsert({**LOT, "price": "90,00"})
        (doc,) = client["trading"]["lots"].docs.values()
        assert doc["price"] == "90,00"


@pytest.mark.parametrize(
    "broken",
    [{"lot_id": "1"}, {"source": "bep"}, {"source": "", "lot_id": "1"}, {"source": "bep", "lot_id": None}],
)
async def test_айтем_без_ключа_не_пишется(broken: dict) -> None:
    client = FakeClient()
    async with store(client) as s:
        with pytest.raises(ValueError, match="ключевых полей"):
            await s.upsert(broken)
        assert client["trading"]["lots"].docs == {}


async def test_count_считает_только_свою_площадку() -> None:
    client = FakeClient()
    async with store(client, "bep") as bep, store(client, "etb") as etb:
        await bep.upsert(LOT)
        await bep.upsert({**LOT, "lot_id": "2"})
        await etb.upsert({"source": "etb", "lot_id": "1"})
        assert await bep.count() == 2
        assert await etb.count() == 1


async def test_ключ_держится_уникальным_индексом() -> None:
    client = FakeClient()
    async with store(client):
        pass
    assert client["trading"]["lots"].indexes == [((("source", 1), ("lot_id", 1)), True)]


async def test_чужой_клиент_не_закрывается() -> None:
    client = FakeClient()
    async with store(client):
        pass
    assert client.closed is False


async def test_после_закрытия_хранилище_не_пишет() -> None:
    client = FakeClient()
    s = store(client)
    await s.close()
    await s.close()  # повторное закрытие безвредно
    with pytest.raises(RuntimeError, match="уже закрыто"):
        await s.upsert(LOT)


async def test_первое_и_последнее_появление_лота() -> None:
    client = FakeClient()
    async with MongoStore("bep", client=client, run_id="r1") as s:
        await s.upsert(LOT)
    (doc,) = client["trading"]["lots"].docs.values()
    first = doc["created_at"]
    assert doc["updated_at"] == first and doc["run_id"] == "r1"

    async with MongoStore("bep", client=client, run_id="r2") as s:
        await s.upsert(LOT)
    (doc,) = client["trading"]["lots"].docs.values()
    assert doc["created_at"] == first  # вставка не повторяется
    assert doc["updated_at"] >= first and doc["run_id"] == "r2"


def test_run_id_по_умолчанию_свой_у_каждого_хранилища() -> None:
    client = FakeClient()
    assert store(client).run_id != store(client).run_id


# ── подключение ──────────────────────────────────────────────────────────────


def test_клиент_по_умолчанию_из_настроек(monkeypatch: pytest.MonkeyPatch) -> None:
    uris: list[str] = []
    monkeypatch.setattr(client_module, "AsyncMongoClient", lambda uri: uris.append(uri) or FakeClient())
    create_client()
    create_client("mongodb://elsewhere:27017")
    assert uris == [conf.mongo.uri, "mongodb://elsewhere:27017"]


async def test_без_чужого_клиента_хранилище_создаёт_и_закрывает_своё(monkeypatch: pytest.MonkeyPatch) -> None:
    own = FakeClient()
    monkeypatch.setattr(storage_module, "create_client", lambda uri: own)
    async with MongoStore("bep") as s:
        await s.upsert(LOT)
    assert own.closed is True
    assert len(own["trading"]["lots"].docs) == 1
