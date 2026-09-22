"""Проверки ``MongoStore`` на подделке коллекции."""

from __future__ import annotations

import pytest

from core.db import MongoStore
from tests.fake_mongo import FakeClient

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
