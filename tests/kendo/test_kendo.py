"""Движок Kendo-ETP на настоящих страницах trade_alliance: листинг и торги 10840."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from collector import CrawlerContext, Request, Response
from parsel import Selector

from tests.helpers import run
from tp.kendo.base import find_next_page, parse_listing
from tp.kendo.detail import detail_of, parse_detail
from tp.kendo.source import PLATFORMS, TradeAlliance

FIXTURES = Path(__file__).parent / "fixtures"
LISTING = (FIXTURES / "listing_trade_alliance.html").read_text(encoding="utf-8")
TRADE = (FIXTURES / "trade_10840.html").read_text(encoding="utf-8")
URL = TradeAlliance.start_urls[0]
TRADE_URL = "https://trade-alliance.ru/oaof/10840"


def crawler(**params: Any) -> TradeAlliance:
    return TradeAlliance(CrawlerContext(http=None, params=params))


async def searching(c: TradeAlliance) -> TradeAlliance:
    """Краулер, прочитавший форму стартовой страницы."""
    await run(c.parse, LISTING, URL)
    return c


def test_площадки() -> None:
    assert set(PLATFORMS) == {"trade_alliance", "seltim", "electro_torgi", "torgi82", "vetp"}
    assert URL == "https://trade-alliance.ru/lots"


def test_листинг_сводится_к_торгам() -> None:
    trades = parse_listing(Selector(LISTING))
    assert len(trades) == len({t["trade_id"] for t in trades}) == 15
    first = trades[0]
    assert (first["trade_id"], first["trade_number"], first["trade_url"]) == (
        "10840",
        "10840–ОАОФ",
        "/oaof/10840",
    )
    assert first["bids_end"] == "29.10.2026 00:00:00"
    assert find_next_page(Selector(LISTING), 1) == 2


async def test_поиск_по_статусам_из_формы_площадки() -> None:
    c = crawler()
    (first,) = await run(c.parse, LISTING, URL)
    assert [choice.label for choice, *_ in c.searches] == ["Объявлен", "Идет прием заявок"]
    assert ("status_id", "3") in first.params and first.metadata == {"search": 0, "page": 1}


async def test_заход_в_торги_следующая_страница_и_предел() -> None:
    c = await searching(crawler())
    out = await run(c.search_page, LISTING, URL, search=0, page=1)
    dives = [r for r in out if "trade" in r.metadata]
    (pager,) = [r for r in out if "trade" not in r.metadata]
    assert len(dives) == 15 and dives[0].url == TRADE_URL
    assert pager.metadata == {"search": 0, "page": 2} and ("page", "2") in pager.params

    c = await searching(crawler(max_pages="1"))
    out = await run(c.search_page, LISTING, URL, search=0, page=1)
    # Предел страниц — переход к следующему статусу, а не к странице 2.
    (nxt,) = [r for r in out if "trade" not in r.metadata]
    assert nxt.metadata == {"search": 1, "page": 1}


async def test_лот_торгов() -> None:
    trade = parse_listing(Selector(LISTING))[0]
    (lot,) = await run(crawler().parse_trade, TRADE, TRADE_URL, trade=trade)
    assert (lot["source"], lot["lot_id"], lot["lot_num"]) == ("trade_alliance", "10840_1", "1")
    assert (lot["lot_url"], lot["trade_url"]) == ("https://trade-alliance.ru/oaof/10840/lots/3472", TRADE_URL)
    assert (lot["price"], lot["price_value"]) == ("135 000.00", 135000.0)
    assert lot["description"].startswith("Лот №1: Транспортное средство")
    assert (lot["organizer"], lot["debtor"]) == ("Козырев Илья Михайлович", "Кезарева Диана Юрьевна")
    assert (lot["status"], lot["is_active"]) == ("Идет прием заявок", True)
    assert lot["bids_end_at"].isoformat() == "2026-10-29T00:00:00+03:00"


def test_детали_лота() -> None:
    details = parse_detail(Selector(TRADE), ["10840_1", "10840_9"])
    assert list(details) == ["10840_1"]
    detail = details["10840_1"]
    assert detail["Лот"]["Номер лота"] == "1"
    assert detail["Сведения о торгах"]["Номер дела о банкротстве"] == "А70-2244/2026"
    assert detail["Документы"] and all(d["url"].startswith("http") for d in detail["Документы"])


async def test_детальный_парсер_один_запрос_на_торги() -> None:
    class Sink:
        async def pending_detail(self, limit: int, statuses: list[str] | None = None) -> Any:
            for lot_id in ("10840_1", "10840_2"):
                yield {"lot_id": lot_id, "lot_url": f"{TRADE_URL}/lots/{lot_id}", "trade_url": TRADE_URL}

    detail = detail_of(TradeAlliance)
    assert (detail.name, detail.settings) == (TradeAlliance.name, TradeAlliance.settings)
    c = detail(CrawlerContext(http=None, sink=Sink()))
    (request,) = [r async for r in c.start_requests()]
    assert (request.url, request.metadata) == (TRADE_URL, {"lot_ids": ["10840_1", "10840_2"]})
    (item,) = await run(c.parse, TRADE, TRADE_URL, lot_ids=["10840_1", "10840_2"])
    assert item["lot_id"] == "10840_1" and "Лот" in item["detail"]


async def test_страница_ошибки_это_ошибка_а_не_пустой_листинг() -> None:
    c = crawler()
    page = Response(SimpleNamespace(status_code=404, text="<html></html>"), Request(url=URL), c)
    with pytest.raises(ValueError, match="404"):
        [out async for out in c.parse(page)]
