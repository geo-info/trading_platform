"""Движок btorg на настоящих страницах atctrade: листинг и фрагмент лотов торгов 13147.

Страницы площадки — в windows-1251; фикстуры хранятся как пришли, байтами.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collector import CrawlerContext
from parsel import Selector

from tests.helpers import run
from tp.btorg.base import XHR, find_next_page, parse_listing, property_details
from tp.btorg.detail import detail_of, parse_detail
from tp.btorg.source import PLATFORMS, Atctrade

FIXTURES = Path(__file__).parent / "fixtures"
LISTING = (FIXTURES / "listing_atctrade.html").read_bytes().decode("cp1251")
LOTS = (FIXTURES / "lots_13147.html").read_bytes().decode("cp1251")
URL = Atctrade.start_urls[0]
LOTS_URL = "https://atctrade.ru/etp/trade/inner-view-lots.html?perspective=inline&id=105491777"


def crawler(**params: Any) -> Atctrade:
    return Atctrade(CrawlerContext(http=None, params=params))


def test_площадки() -> None:
    assert len(PLATFORMS) == 6 and URL == "https://atctrade.ru/etp/trade/list.html"


def test_листинг_организатор_и_должник_на_своих_местах() -> None:
    """Колонка «Организатор» идёт перед «Должником»."""
    trades = parse_listing(Selector(LISTING))
    assert len(trades) == 15 and find_next_page(Selector(LISTING), 1) == 2
    first = trades[0]
    assert (first["trade_id"], first["trade_number"], first["trade_type"]) == ("13147", "13147-ОТПП", "ОТПП")
    assert first["organizer"] == "Бычкова Юлия Витальевна"
    assert first["debtor"] == "Цыганова Анна Владимировна"
    assert first["bids_start"] == "28.09.2026 08:00"
    assert first["trade_page"] == "/trade/view/purchase/general.html?id=105491777"


async def test_заход_за_фрагментом_лотов_как_xhr() -> None:
    c = crawler()
    await run(c.parse, LISTING, URL)
    out = await run(c.search_page, LISTING, URL, search=0, page=1)
    dives = [r for r in out if "trade" in r.metadata]
    assert len(dives) == 15
    assert (dives[0].url, dives[0].headers) == (LOTS_URL, XHR)


async def test_лот_публичного_предложения() -> None:
    trade = parse_listing(Selector(LISTING))[0]
    (lot,) = await run(crawler().parse_trade, LOTS, LOTS_URL, trade=trade)
    assert (lot["lot_id"], lot["price_value"], lot["status"]) == ("13147_1", 333000.0, "объявлены")
    assert (lot["organizer"], lot["debtor"]) == ("Бычкова Юлия Витальевна", "Цыганова Анна Владимировна")
    assert lot["lot_url"] == "https://atctrade.ru/trade/view/purchase/general.html?id=105491777"
    assert lot["trade_url"] == LOTS_URL
    # Срок приёма — конец последнего интервала, а не начало приёма из листинга.
    assert lot["bids_end"] == "22.10.2026 17:00"


def test_детали_лота() -> None:
    detail = parse_detail(Selector(LOTS), ["13147_1"])["13147_1"]
    # Интервалы снижения цены — в графике, а не датами-подписями среди пар лота.
    assert len(detail["График снижения цены"]) == 5
    assert detail["График снижения цены"][0]["Цена на периоде, руб."] == "333 000,00"
    assert not any(label[:2].isdigit() for label in detail["Лот"])
    assert detail["Лот"]["Классификатор имущества"] == "0106008. Автомобили"


def test_детальный_парсер_ходит_за_фрагментом_как_xhr() -> None:
    assert detail_of(Atctrade).DETAIL_HEADERS == XHR


def test_описание_без_предмета_торгов_из_сведений_об_имуществе() -> None:
    pairs = {"Cведения об имуществе (предприятии) должника": "Datsun on-DO", "Статус торгов": "объявлены"}
    assert property_details(pairs) == "Datsun on-DO"
