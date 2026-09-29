"""Движок btorg: листинг, пейджер, фрагмент лотов, адрес лота для человека и поток краулера."""

from __future__ import annotations

import pytest
from collector import Request
from parsel import Selector

from core.lot import Lot
from tests.conftest import collect, make, page, read_fixture, respond
from tp.btorg.base import find_next_page, parse_listing, parse_lots, property_details
from tp.btorg.source import Atctrade

LISTING = "btorg/fixtures/listing_atctrade.html"
LOTS = "btorg/fixtures/lots_13147.html"
ENC = "cp1251"


def _listing() -> Selector:
    return page(LISTING, ENC)


def _lots() -> Selector:
    return page(LOTS, ENC)


def test_листинг() -> None:
    trades = parse_listing(_listing())
    assert len(trades) == 15
    first = trades[0]
    assert first["trade_id"] == "13147"
    assert first["trade_number"] == "13147-ОТПП"
    assert first["trade_type"] == "ОТПП"
    assert first["trade_url"] == "/etp/trade/inner-view-lots.html?perspective=inline&id=105491777"
    assert first["page_url"] == "/trade/view/purchase/general.html?id=105491777"


def test_пейджер() -> None:
    assert find_next_page(_listing(), 1) == (2, "/etp/trade/list.html?page=2")


def test_последняя_страница() -> None:
    assert find_next_page(_listing(), 999) is None


def test_лоты_фрагмента() -> None:
    trade = {"trade_id": "13147", "trade_number": "13147-ОТПП", "trade_type": "ОТПП"}
    (lot,) = parse_lots(_lots(), trade)
    assert lot["lot_id"] == "13147_1"
    assert lot["description"] == "Транспортное средство"
    assert lot["price"].startswith("333 000,00 руб")
    assert lot["bids_end"] == "22.10.2026 17:00"


def test_описание_из_сведений_если_предмет_пуст() -> None:
    assert property_details({"Cведения об имуществе должника": "X"}) == "X"  # первая «C» латинская
    assert property_details({"Предмет торгов": "Y"}) is None

    fragment = Selector(
        '<table id="lotNumber1">'
        "<tr><td>Предмет торгов</td><td></td></tr>"
        "<tr><td>Cведения об имуществе должника</td><td>Квартира</td></tr>"
        "<tr><td>Начальная цена продажи имущества</td><td>1 000,00 руб</td></tr>"
        "</table>"
    )
    (lot,) = parse_lots(fragment, {"trade_id": "1"})
    assert lot["description"] == "Квартира"
    assert lot["bids_end"] is None


def test_start_urls() -> None:
    assert Atctrade.start_urls == ["https://atctrade.ru/etp/trade/list.html"]


async def _listing_flow(c: Atctrade) -> tuple[list[Request], list]:
    req = Request(url=Atctrade.start_urls[0])
    return await collect(c.parse(respond(c, req, read_fixture(LISTING, ENC))))


async def test_parse_поток() -> None:
    c = make(Atctrade)
    requests, items = await _listing_flow(c)

    assert items == []
    trade_requests = [r for r in requests if r.callback == c.parse_trade]
    assert len(trade_requests) == 15
    assert all(r.headers["X-Requested-With"] == "XMLHttpRequest" for r in trade_requests)
    assert all(r.url.startswith("https://atctrade.ru/etp/trade/inner-view-lots.html") for r in trade_requests)
    (nxt,) = [r for r in requests if r.callback != c.parse_trade]
    assert nxt.url == "https://atctrade.ru/etp/trade/list.html?page=2"
    assert nxt.metadata == {"num_page": 2}


async def test_max_pages() -> None:
    c = make(Atctrade, params={"max_pages": 1})
    requests, _ = await _listing_flow(c)
    assert len(requests) == 15
    assert all(r.callback == c.parse_trade for r in requests)


async def test_parse_trade_отдаёт_lot() -> None:
    c = make(Atctrade)
    requests, _ = await _listing_flow(c)
    (request,) = [r for r in requests if r.metadata.get("trade", {}).get("trade_id") == "13147"]

    _, items = await collect(c.parse_trade(respond(c, request, read_fixture(LOTS, ENC))))

    (item,) = items
    Lot.model_validate({k: v for k, v in item.items() if k in Lot.model_fields})
    assert item["lot_url"] == "https://atctrade.ru/trade/view/purchase/general.html?id=105491777"
    assert (
        item["trade_url"]
        == "https://atctrade.ru/etp/trade/inner-view-lots.html?perspective=inline&id=105491777"
    )
    assert item["price_value"] == 333000.0
    assert "price_schedule" not in item


async def test_не_200() -> None:
    c = make(Atctrade)
    req = Request(url=Atctrade.start_urls[0], metadata={"trade": {"trade_id": "1"}})
    with pytest.raises(ValueError, match="500"):
        await collect(c.parse(respond(c, req, "", status=500)))
    with pytest.raises(ValueError, match="503"):
        await collect(c.parse_trade(respond(c, req, "", status=503)))
