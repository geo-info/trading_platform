"""Движок btorg на настоящих страницах atctrade: листинг и фрагмент лотов торгов 13147.

Страницы площадки — в windows-1251; фикстуры хранятся как пришли, байтами.
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from collector import CrawlerContext, Request, Response
from parsel import Selector

from tp.marking.btorg import find_next_page, parse_listing, property_details
from tp.platforms.btorg.atctrade import Atctrade

FIXTURES = Path(__file__).parent / "fixtures"
LISTING = (FIXTURES / "listing_atctrade.html").read_bytes().decode("cp1251")
LOTS = (FIXTURES / "lots_13147.html").read_bytes().decode("cp1251")
URL = Atctrade.start_urls[0]
LOTS_URL = "https://atctrade.ru/etp/trade/inner-view-lots.html?perspective=inline&id=105491777"


def crawler(**params: Any) -> Atctrade:
    return Atctrade(CrawlerContext(http=None, params=params))


async def run(method: Any, html: str, url: str, **metadata: Any) -> list[Any]:
    page = Response(
        SimpleNamespace(status_code=200, text=html), Request(url=url, metadata=metadata), method.__self__
    )
    return [out async for out in method(page)]


def test_листинг_организатор_и_должник_на_своих_местах() -> None:
    """В coll-temp они были перепутаны: колонка «Организатор» идёт перед «Должником»."""
    trades = parse_listing(Selector(LISTING))
    assert len(trades) == 15 and find_next_page(Selector(LISTING), 1) == 2
    first = trades[0]
    assert (first["trade_id"], first["trade_number"], first["trade_type"]) == ("13147", "13147-ОТПП", "ОТПП")
    assert first["organizer"] == "Бычкова Юлия Витальевна"
    assert first["debtor"] == "Цыганова Анна Владимировна"
    assert first["bids_start"] == "28.09.2026 08:00"


async def test_заход_за_фрагментом_лотов_как_xhr() -> None:
    requests = await run(crawler().parse, LISTING, URL)
    dives = [r for r in requests if "trade" in r.metadata]
    assert len(dives) == 15
    assert dives[0].url == LOTS_URL
    assert dives[0].headers == {"X-Requested-With": "XMLHttpRequest"}


async def test_окно_по_дате_на_btorg_не_действует() -> None:
    """В листинге только начало приёма заявок — остановка по нему теряла бы идущие торги."""
    requests = await run(crawler(since="2030-01-01").parse, LISTING, URL)
    assert [r for r in requests if "trade" not in r.metadata]


async def test_лот_публичного_предложения() -> None:
    trade = parse_listing(Selector(LISTING))[0]
    (lot,) = await run(crawler().parse_trade, LOTS, LOTS_URL, trade=trade)

    assert (lot["lot_id"], lot["price"], lot["status"]) == ("13147_1", 333000.0, "объявлены")
    assert (lot["organizer"], lot["debtor"]) == ("Бычкова Юлия Витальевна", "Цыганова Анна Владимировна")
    # Интервалы снижения цены — в price_schedule, а не датами-подписями в extra.
    assert len(lot["price_schedule"]) == 5
    assert lot["price_schedule"][0]["Цена на периоде, руб."] == "333 000,00"
    assert not any(label[:2].isdigit() for label in lot["extra"])
    assert lot["extra"]["Классификатор имущества"] == "0106008. Автомобили"
    # Срок приёма — конец последнего интервала, а не начало приёма из листинга.
    assert lot["bidding_date_raw"] == "22.10.2026 17:00"
    assert lot["extra"]["Начало приема заявок"] == "28.09.2026 08:00"
    assert lot["validation"]["ok"] is True


def test_описание_без_предмета_торгов_из_сведений_об_имуществе() -> None:
    detail = {"Cведения об имуществе (предприятии) должника": "Datsun on-DO", "Статус торгов": "объявлены"}
    assert property_details(detail) == "Datsun on-DO"
