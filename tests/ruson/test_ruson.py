"""Движок rus-on на настоящих страницах: листинги nistp и rus_on, торги nistp 496200."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collector import CrawlerContext
from parsel import Selector

from tests.helpers import run
from tp.ruson.base import header, parse_listing
from tp.ruson.detail import parse_detail
from tp.ruson.source import PLATFORMS, Nistp, Sistematorg

FIXTURES = Path(__file__).parent / "fixtures"
NISTP = (FIXTURES / "listing_nistp.html").read_text(encoding="utf-8")
RUS_ON = (FIXTURES / "listing_rus_on.html").read_text(encoding="utf-8")
TRADE = (FIXTURES / "trade_496200.html").read_text(encoding="utf-8")
URL = Nistp.start_urls[0]
TRADE_URL = "https://nistp.ru/bankrot/trade_view.php?trade_nid=496200"


def crawler(**params: Any) -> Nistp:
    return Nistp(CrawlerContext(http=None, params=params))


def test_площадки_и_путь_листинга() -> None:
    assert len(PLATFORMS) == 5
    assert Sistematorg.start_urls == ["https://sistematorg.com/tradelist.php"]
    assert URL == "https://nistp.ru/bankrot/trade_list.php"


def test_колонки_по_заголовку_без_строки_поиска() -> None:
    """Над таблицей rus_on — строка поиска со своим <th>: номера колонок не должны съезжать."""
    assert header(Selector(RUS_ON))[0] == "номер торгов"
    first = parse_listing(Selector(RUS_ON))[0]
    assert (first["trade_id"], first["organizer"], first["bids_end"]) == (
        "14403",
        "Третьякова Галина Анатольевна",
        "11.10.2026 12:00",
    )


def test_листинг_nistp() -> None:
    trades = parse_listing(Selector(NISTP))
    assert len(trades) == len({t["trade_nid"] for t in trades}) == 20
    first = trades[0]
    assert (first["trade_id"], first["trade_number"], first["trade_url"]) == ("70700", "70700-ОТПП", TRADE_URL)
    assert (first["status"], first["bids_end"]) == ("Прием заявок", "04.11.2026 10:00")


async def test_следующая_страница_это_pagenum() -> None:
    c = crawler()
    await run(c.parse, NISTP, URL)
    out = await run(c.search_page, NISTP, URL, search=0, page=1)
    (pager,) = [r for r in out if "trade" not in r.metadata]
    assert pager.metadata == {"search": 0, "page": 2} and pager.method == "GET"
    assert [value for name, value in pager.params if name == "pagenum"] == ["2"]


async def test_лоты_торгов() -> None:
    trade = parse_listing(Selector(NISTP))[0]
    lots = await run(crawler().parse_trade, TRADE, TRADE_URL, trade=trade)
    # Номера лотов на площадке такие.
    assert [lot["lot_id"] for lot in lots] == ["70700_1", "70700_4", "70700_7"]
    lot = lots[0]
    assert (lot["price_value"], lot["status"], lot["is_active"]) == (21434427.98, "Прием заявок", True)
    assert (lot["organizer"], lot["debtor"]) == ("Александров Игорь Олегович", "Вейс Андрей Эдгарович")
    assert lot["description"] == "Земельные участки в количестве 10 единиц"
    assert lot["bids_end"] == "04.11.2026 10:00:00"
    # У публичного предложения даты торгов нет вовсе.
    assert lot["auction_at"] is None
    assert lot["lot_url"] == lot["trade_url"] == TRADE_URL


def test_детали_лота() -> None:
    details = parse_detail(Selector(TRADE), ["70700_1", "70700_4", "70700_2"])
    assert list(details) == ["70700_1", "70700_4"]
    detail = details["70700_1"]
    assert detail["Лот"]["Наименование имущества"] == "Земельные участки в количестве 10 единиц"
    assert detail["Должник"]["Фамилия"] == "Вейс"
    assert "Организатор" in detail
