import asyncio
from datetime import UTC, datetime

import pytest

from core.lot import is_active_status
from core.trade_type import normalize_trade_type, resolve_trade_type
from tp.scripts.common import Result, report


def test_unknown_status_is_not_confirmed_active():
    assert is_active_status(None) is None
    assert is_active_status("Неизвестный новый статус") is None


def test_partial_result_is_not_success():
    result = Result("example", done=1, errors=50, reason="max_errors")
    assert result.outcome == "partial"
    assert report([result], "лотов", "новых") == 1


@pytest.mark.mongo
async def test_listing_does_not_replace_explicit_detail(storage, clock):
    item = {
        "source": "bep",
        "lot_id": "1",
        "lot_url": "https://x/1",
        **normalize_trade_type("ОАОФ", source="listing"),
    }
    await storage.upsert(item)
    title = "Открытый аукцион с открытой формой представления предложений о цене (Банкротство)"
    await storage.save_detail("1", {"Тип торгов": title}, clock.now())
    before = await storage.collection.find_one({"lot_id": "1"})
    await storage.upsert(item)
    after = await storage.collection.find_one({"lot_id": "1"})
    assert after["trade_type"] == title
    assert after["updated_at"] == before["updated_at"]
    assert after["last_seen_at"] > before["last_seen_at"]
    assert [x async for x in storage.pending_detail()] == []


@pytest.mark.mongo
async def test_old_detail_cannot_replace_newer(storage, clock):
    await storage.upsert({"source": "bep", "lot_id": "1", "lot_url": "x"})
    old = clock.now()
    await storage.save_detail("1", {"Описание": "new"}, clock.now())
    await storage.save_detail("1", {"Описание": "old"}, old)
    doc = await storage.collection.find_one({"lot_id": "1"})
    assert doc["detail"]["Описание"] == "new"


@pytest.mark.mongo
async def test_missing_detail_has_explicit_state(storage):
    await storage.upsert({"source": "bep", "lot_id": "1", "lot_url": "x"})
    await storage.save_detail("1", None, datetime.now(UTC))
    doc = await storage.collection.find_one({"lot_id": "1"})
    assert doc["detail_state"] == "not_found"


def test_conflicting_attributes_are_explained():
    title = "Открытый аукцион с открытой формой представления цены"
    result = resolve_trade_type({"Тип торгов": title, "Форма представления предложений о цене": "Закрытая"})
    assert result["trade_type_raw"] == title
    assert result["trade_price_form"] == "закрытая"
    assert result["trade_type_conflicts"] == [
        {
            "field": "trade_price_form",
            "from_type": "открытая",
            "explicit": "закрытая",
            "source": "page:Форма представления предложений о цене",
        }
    ]


@pytest.mark.mongo
async def test_concurrent_writes_keep_detail_and_unique_lot(storage, clock):
    item = {"source": "bep", "lot_id": "1", "lot_url": "x"}
    await asyncio.gather(*(storage.upsert(item) for _ in range(8)))
    at = clock.now()
    await asyncio.gather(storage.upsert(item), storage.save_detail("1", {"Описание": "дом"}, at))
    assert await storage.count() == 1
    doc = await storage.collection.find_one({"lot_id": "1"})
    assert doc["detail"] == {"Описание": "дом"}
    assert doc["listing"] == item
    assert doc["revision"] == 10


@pytest.mark.mongo
async def test_changed_listing_type_invalidates_old_projection(storage, clock):
    item = {"source": "bep", "lot_id": "1", "lot_url": "x", **normalize_trade_type("ОАОФ")}
    await storage.upsert(item)
    await storage.save_detail("1", {"Тип торгов": "Открытый аукцион"}, clock.now())
    await storage.upsert({**item, **normalize_trade_type("ОТПП")})
    doc = await storage.collection.find_one({"lot_id": "1"})
    assert doc["trade_kind"] == "публичное предложение"
    assert len([x async for x in storage.pending_detail()]) == 1


def test_deliberate_limit_is_partial():
    assert Result("x", done=10, reason="done", limited=True).outcome == "partial"
    assert Result("x", done=10, reason="done").outcome == "complete"
