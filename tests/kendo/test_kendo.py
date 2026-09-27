"""Движок Kendo-ETP на настоящих страницах trade_alliance: листинг и торги 10840.

Тесты гоняют ``parse()`` и ``parse_trade()`` площадки и смотрят, что они
отдают: запросы захода и следующей страницы, айтемы лотов.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from collector import CrawlerContext, Request, Response
from parsel import Selector

from tp.marking.kendo import find_next_page, parse_listing
from tp.platforms.kendo.trade_alliance import TradeAlliance

FIXTURES = Path(__file__).parent / "fixtures"
LISTING = (FIXTURES / "listing_trade_alliance.html").read_text(encoding="utf-8")
TRADE = (FIXTURES / "trade_10840.html").read_text(encoding="utf-8")
URL = TradeAlliance.start_urls[0]
TRADE_URL = "https://trade-alliance.ru/oaof/10840"


def crawler(**params: Any) -> TradeAlliance:
    return TradeAlliance(CrawlerContext(http=None, params=params))


async def run(method: Any, html: str, url: str, **metadata: Any) -> list[Any]:
    page = Response(
        SimpleNamespace(status_code=200, text=html), Request(url=url, metadata=metadata), method.__self__
    )
    return [out async for out in method(page)]


def pagers(requests: list[Request]) -> list[Request]:
    return [r for r in requests if "trade" not in r.metadata]


# ── листинг ──────────────────────────────────────────────────────────────────


def test_листинг_сводится_к_торгам() -> None:
    trades = parse_listing(Selector(LISTING))
    assert len(trades) == len({t["trade_id"] for t in trades}) == 15
    first = trades[0]
    assert (first["trade_id"], first["trade_number"], first["detail_url"]) == (
        "10840",
        "10840–ОАОФ",
        "/oaof/10840",
    )
    assert first["bidding_date"] == "29.10.2026 00:00:00"
    assert find_next_page(Selector(LISTING), 1) == 2


async def test_заход_в_каждые_торги_и_следующая_страница() -> None:
    requests = await run(crawler().parse, LISTING, URL)
    dives = [r for r in requests if "trade" in r.metadata]
    (pager,) = pagers(requests)
    assert len(dives) == 15 and dives[0].url == TRADE_URL
    assert (pager.url, pager.metadata) == (f"{URL}?page=2", {"page": 2})


async def test_предел_страниц_и_окно_по_дате() -> None:
    assert pagers(await run(crawler(max_pages="1").parse, LISTING, URL)) == []
    # Сроки приёма на странице — 2026 год: окно с 2027-го останавливает листание.
    assert pagers(await run(crawler(since="2027-01-01").parse, LISTING, URL)) == []
    assert pagers(await run(crawler(since="2026-01-01").parse, LISTING, URL))


# ── торги ────────────────────────────────────────────────────────────────────


async def test_лот_торгов_через_модель() -> None:
    trade = parse_listing(Selector(LISTING))[0]
    (lot,) = await run(crawler().parse_trade, TRADE, TRADE_URL, trade=trade)

    assert (lot["source"], lot["lot_id"], lot["lot_num"]) == ("trade_alliance", "10840_1", "1")
    assert lot["url"] == "https://trade-alliance.ru/oaof/10840/lots/3472"
    assert (lot["price"], lot["price_raw"]) == (135000.0, "135 000.00")
    assert lot["description"].startswith("Лот №1: Транспортное средство")
    assert lot["organizer"] == lot["extra"]["Наименование"] == "Козырев Илья Михайлович"
    assert lot["attachments"] and all(a["url"].startswith("http") for a in lot["attachments"])
    assert lot["validation"] == {"ok": True, "errors": [], "unknown_labels": []}


async def test_лот_который_модель_не_пропустила_сохраняется() -> None:
    """Без номера торгов Lot не собирается — лот пишется запасным документом."""
    trade = {**parse_listing(Selector(LISTING))[0], "trade_id": None}
    (lot,) = await run(crawler().parse_trade, TRADE, TRADE_URL, trade=trade)
    assert (lot["source"], lot["lot_id"]) == ("trade_alliance", "None_1")
    assert lot["row"]["price_raw"] == "135 000.00"
    assert lot["validation"]["ok"] is False and "trade_id" in lot["validation"]["errors"][0]


async def test_страница_ошибки_это_ошибка_а_не_пустой_листинг() -> None:
    page = Response(SimpleNamespace(status_code=404, text="<html></html>"), Request(url=URL), crawler())
    with pytest.raises(ValueError, match="404"):
        [out async for out in crawler().parse(page)]
