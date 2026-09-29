"""Движок Kendo: листинг, пейджер без схемы, лоты страницы торгов и поток краулера."""

from __future__ import annotations

import pytest
from collector import Request
from parsel import Selector

from core.lot import Lot
from tests.conftest import collect, make, page, read_fixture, respond
from tp.kendo.base import debtor_of, find_next_page, parse_listing, parse_lots
from tp.kendo.source import TradeAlliance, Vetp

LISTING = "kendo/fixtures/listing_trade_alliance.html"
TRADE = "kendo/fixtures/trade_10840.html"


def test_листинг() -> None:
    trades = parse_listing(page(LISTING))
    assert len(trades) == 15
    first = trades[0]
    assert first["trade_id"] == "10840"
    assert first["trade_number"] == "10840–ОАОФ"
    assert first["trade_type"] == "ОАОФ"
    assert first["trade_url"] == "/oaof/10840"
    assert first["bids_end"] == "29.10.2026 00:00:00"
    assert first["trade_title"].endswith("должник Кезарева Диана Юрьевна")
    assert {t["trade_type"] for t in trades} == {"ОАОФ", "ОТПП"}


def test_номер_с_дефисом() -> None:
    card = Selector('<div class="block-lot"><div class="bold"><a href="/oaof/37">37-ОАОФ</a></div></div>')
    (trade,) = parse_listing(card)
    assert trade["trade_type"] == "ОАОФ"
    assert trade["trade_url"] == "/oaof/37"


def test_пейджер_без_схемы() -> None:
    assert find_next_page(page(LISTING), 1) == (2, "/lots?page=2")


def test_последняя_страница() -> None:
    assert find_next_page(page(LISTING), 999) is None


def test_debtor_of() -> None:
    assert debtor_of("Лот, должник Иванов И.И.") == "Иванов И.И."
    assert debtor_of("Лот, должника ООО Ромашка") == "ООО Ромашка"
    assert debtor_of(None) is None
    assert debtor_of("Лот без указания") is None


def test_лоты_страницы_торгов() -> None:
    trade = {
        "trade_id": "10840",
        "trade_number": "10840–ОАОФ",
        "trade_type": "ОАОФ",
        "trade_title": "Имущество, должник Кезарева Диана Юрьевна",
        "bids_end": None,
    }
    (lot,) = parse_lots(page(TRADE), trade)
    assert lot["lot_id"] == "10840_1"
    assert lot["lot_num"] == "1"
    assert lot["lot_href"] == "https://trade-alliance.ru/oaof/10840/lots/3472"
    assert lot["price"] == "135 000.00"
    assert lot["status"] == "Идет прием заявок"
    assert lot["organizer"] == "Козырев Илья Михайлович"
    assert lot["debtor"] == "Кезарева Диана Юрьевна"
    assert lot["bids_end"] == "29.10.2026 00:00:00"
    assert lot["auction_date"] == "02.11.2026 09:30:00"


def test_start_urls() -> None:
    assert TradeAlliance.start_urls == ["https://trade-alliance.ru/lots"]
    assert Vetp.start_urls == ["https://банкрот.вэтп.рф/lots"]


async def _listing_flow(c: TradeAlliance) -> tuple[list[Request], list]:
    req = Request(url=TradeAlliance.start_urls[0])
    return await collect(c.parse(respond(c, req, read_fixture(LISTING))))


async def test_parse_поток() -> None:
    c = make(TradeAlliance)
    requests, items = await _listing_flow(c)

    assert items == []
    assert all(r.url.startswith("https://") for r in requests)
    trade_requests = [r for r in requests if r.callback == c.parse_trade]
    assert len(trade_requests) == 15
    assert all(r.metadata["trade"]["trade_id"] for r in trade_requests)
    (nxt,) = [r for r in requests if r.callback != c.parse_trade]
    assert nxt.url == "https://trade-alliance.ru/lots?page=2"
    assert nxt.metadata == {"num_page": 2}


async def test_max_pages() -> None:
    c = make(TradeAlliance, params={"max_pages": 1})
    requests, _ = await _listing_flow(c)
    assert len(requests) == 15
    assert all(r.callback == c.parse_trade for r in requests)


async def test_parse_trade_отдаёт_lot() -> None:
    c = make(TradeAlliance)
    requests, _ = await _listing_flow(c)
    (request,) = [r for r in requests if r.metadata.get("trade", {}).get("trade_id") == "10840"]

    _, items = await collect(c.parse_trade(respond(c, request, read_fixture(TRADE))))

    (item,) = items
    Lot.model_validate({k: v for k, v in item.items() if k in Lot.model_fields})
    assert item["trade_url"] == "https://trade-alliance.ru/oaof/10840"
    assert item["lot_url"] == "https://trade-alliance.ru/oaof/10840/lots/3472"
    assert item["price_value"] == 135000.0
    assert "lot_href" not in item


async def test_не_200() -> None:
    c = make(TradeAlliance)
    req = Request(url=TradeAlliance.start_urls[0], metadata={"trade": {"trade_id": "1"}})
    with pytest.raises(ValueError, match="500"):
        await collect(c.parse(respond(c, req, "", status=500)))
    with pytest.raises(ValueError, match="503"):
        await collect(c.parse_trade(respond(c, req, "", status=503)))
