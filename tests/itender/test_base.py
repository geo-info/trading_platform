"""Движок iTender: разбор листинга, пейджер и поток краулера (лоты + POST на следующую страницу)."""

from __future__ import annotations

import pytest
from collector import Request

from tests.conftest import collect, make, page, read_fixture, respond
from tp.itender.base import ITender, find_next_target, parse_rows
from tp.itender.source import Centerr
from tp.platforms import platforms

LISTING = "itender/fixtures/listing_centerr.html"
BLOCK_TARGET = "ctl00$ctl00$MainContent$ContentPlaceHolderMiddle$PurchasesSearchResult$ctl01$ctl11"
NEXT_TARGET = "ctl00$ctl00$MainContent$ContentPlaceHolderMiddle$PurchasesSearchResult$ctl01$ctl02"


def test_строки_листинга() -> None:
    rows = parse_rows(page(LISTING))
    assert len(rows) == 20
    first = rows[0]
    assert first["lot_url"] == "/public/auctions/lots/view/1170229/"
    assert first["trade_id"] == "0100660"
    assert first["lot_num"] == "1"
    assert first["price"] == "17 370 000,00"
    assert first["organizer"] == "Ипатьева Наталья Александровна"
    assert first["bids_end"] == "29.10.2026 18:00 (35 дн.)"
    assert first["auction_date"] == "03.11.2026 15:00"
    assert first["status"] == "Прием заявок"
    assert first["winner"] is None
    assert first["trade_type"] == "Открытый аукцион с открытой формой представления цены"
    assert set(first) == {
        "lot_url",
        "trade_id",
        "auction_name",
        "lot_num",
        "description",
        "price",
        "organizer",
        "bids_end",
        "auction_date",
        "status",
        "winner",
        "trade_type",
    }


def test_следующая_страница_и_блок() -> None:
    p = page(LISTING)
    assert find_next_target(p, 1) == NEXT_TARGET
    assert find_next_target(p, 10) == BLOCK_TARGET


def test_start_urls_из_домена() -> None:
    assert platforms(ITender)["centerr"].start_urls == ["https://bankrupt.centerr.ru/public/purchases-all/"]


async def test_parse_отдаёт_лоты_и_следующую_страницу() -> None:
    c = make(Centerr)
    req = Request(url=Centerr.start_urls[0])
    requests, items = await collect(c.parse(respond(c, req, read_fixture(LISTING))))

    assert len(items) == 20
    assert items[0]["source"] == "centerr"
    assert items[0]["lot_id"] == "1170229"
    assert items[0]["lot_url"] == "https://bankrupt.centerr.ru/public/auctions/lots/view/1170229/"

    assert len(requests) == 1
    nxt = requests[0]
    assert nxt.method == "POST"
    assert nxt.metadata == {"num_page": 2}
    assert dict(nxt.data)["__EVENTTARGET"] == NEXT_TARGET


async def test_max_pages_останавливает() -> None:
    c = make(Centerr, params={"max_pages": 1})
    req = Request(url=Centerr.start_urls[0])
    requests, items = await collect(c.parse(respond(c, req, read_fixture(LISTING))))
    assert requests == []
    assert len(items) == 20


async def test_не_200_ошибка() -> None:
    c = make(Centerr)
    req = Request(url=Centerr.start_urls[0])
    with pytest.raises(ValueError, match="500"):
        await collect(c.parse(respond(c, req, "", status=500)))
