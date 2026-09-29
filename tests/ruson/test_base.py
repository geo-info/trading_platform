"""Движок rus-on: листинги разной вёрстки, пейджер ``pagenum_send``, лоты страницы торгов и поток краулера."""

from __future__ import annotations

import pytest
from collector import Request
from parsel import Selector

from core.lot import Lot
from tests.conftest import collect, make, page, read_fixture, respond
from tp.ruson.base import find_next_page, parse_listing, parse_lots, trade_code
from tp.ruson.source import ElTorg, Nistp, Promkonsalt, RusOn, Sistematorg

NISTP = "ruson/fixtures/listing_nistp.html"
RUS_ON = "ruson/fixtures/listing_rus_on.html"
TRADE = "ruson/fixtures/trade_496200.html"


def _trade() -> Selector:
    return page(TRADE)


def test_листинги() -> None:
    nistp = parse_listing(page(NISTP))
    assert len(nistp) == 20
    assert nistp[0]["trade_url"] == "/bankrot/trade_view.php?trade_nid=496200"
    assert len(parse_listing(page(RUS_ON))) == 19


@pytest.mark.parametrize("fixture", [RUS_ON, NISTP])
@pytest.mark.parametrize(("num_page", "expected"), [(1, 2), (5, 6), (9, 10), (10, None)])
def test_пейджер(fixture: str, num_page: int, expected: int | None) -> None:
    assert find_next_page(page(fixture), num_page) == expected


def test_trade_code() -> None:
    assert trade_code("Торги 70700-ОТПП от 01.01.2026") == "70700-ОТПП"
    assert trade_code("без кода") is None


def test_лоты_страницы_торгов() -> None:
    lots = parse_lots(_trade(), {"trade_id": "496200"})
    assert [lot["lot_num"] for lot in lots] == ["1", "4", "7"]
    for lot in lots:
        assert lot["price"]
        assert lot["organizer"]
        assert lot["debtor"]


def test_start_urls() -> None:
    assert Sistematorg.start_urls == ["https://sistematorg.com/tradelist.php"]
    assert Promkonsalt.start_urls == ["https://promkonsalt.ru/tradelist.php"]
    assert Nistp.start_urls == ["https://nistp.ru/bankrot/trade_list.php"]
    assert ElTorg.start_urls == ["https://el-torg.com/bankrot/trade_list.php"]
    assert RusOn.start_urls == ["https://rus-on.ru/bankrot/trade_list.php"]


async def _listing_flow(c: RusOn) -> tuple[list[Request], list]:
    req = Request(url=RusOn.start_urls[0])
    return await collect(c.parse(respond(c, req, read_fixture(RUS_ON))))


async def test_parse_поток() -> None:
    c = make(RusOn)
    requests, items = await _listing_flow(c)

    assert items == []
    trade_requests = [r for r in requests if r.callback == c.parse_trade]
    assert len(trade_requests) == 19
    assert all(r.url.startswith("https://") for r in requests)
    (nxt,) = [r for r in requests if r.callback != c.parse_trade]
    assert nxt.url == "https://rus-on.ru/bankrot/trade_list.php"
    assert nxt.params == {"pagenum": 2}
    assert nxt.metadata == {"num_page": 2}


async def test_max_pages() -> None:
    c = make(RusOn, params={"max_pages": 1})
    requests, _ = await _listing_flow(c)
    assert len(requests) == 19
    assert all(r.callback == c.parse_trade for r in requests)


async def test_parse_trade_отдаёт_lot() -> None:
    c = make(Nistp)
    req = Request(
        url="https://nistp.ru/bankrot/trade_view.php?trade_nid=496200",
        metadata={"trade": {"trade_id": "496200"}},
    )

    _, items = await collect(c.parse_trade(respond(c, req, read_fixture(TRADE))))

    assert len(items) == 3
    for item in items:
        Lot.model_validate({k: v for k, v in item.items() if k in Lot.model_fields})
        assert item["lot_url"] == item["trade_url"] == req.url


async def test_не_200() -> None:
    c = make(RusOn)
    req = Request(url=RusOn.start_urls[0])
    with pytest.raises(ValueError, match="503"):
        await collect(c.parse(respond(c, req, "", status=503)))
    with pytest.raises(ValueError, match="404"):
        await collect(c.parse_trade(respond(c, req, "", status=404)))
