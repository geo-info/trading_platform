"""Движок rus-on на настоящих страницах: листинги nistp и rus_on, торги nistp 496200."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

from collector import CrawlerContext, Request, Response
from parsel import Selector

from tp.marking.ruson import header, parse_listing
from tp.platforms.ruson.nistp import Nistp
from tp.platforms.ruson.sistematorg import Sistematorg

FIXTURES = Path(__file__).parent / "fixtures"
NISTP = (FIXTURES / "listing_nistp.html").read_text(encoding="utf-8")
RUS_ON = (FIXTURES / "listing_rus_on.html").read_text(encoding="utf-8")
TRADE = (FIXTURES / "trade_496200.html").read_text(encoding="utf-8")
URL = Nistp.start_urls[0]
TRADE_URL = "https://nistp.ru/bankrot/trade_view.php?trade_nid=496200"


def crawler(**params: Any) -> Nistp:
    return Nistp(CrawlerContext(http=None, params=params))


async def run(method: Any, html: str, url: str, **metadata: Any) -> list[Any]:
    page = Response(
        SimpleNamespace(status_code=200, text=html), Request(url=url, metadata=metadata), method.__self__
    )
    return [out async for out in method(page)]


def test_колонки_по_заголовку_без_строки_поиска() -> None:
    """Над таблицей rus_on — строка поиска со своим <th>; в coll-temp номера колонок съезжали."""
    assert header(Selector(RUS_ON))[0] == "номер торгов"
    first = parse_listing(Selector(RUS_ON))[0]
    assert (first["trade_id"], first["organizer"], first["bidding_date"]) == (
        "14403",
        "Третьякова Галина Анатольевна",
        "11.10.2026 12:00",
    )


def test_листинг_nistp() -> None:
    trades = parse_listing(Selector(NISTP))
    assert len(trades) == len({t["trade_nid"] for t in trades}) == 20
    first = trades[0]
    assert (first["trade_id"], first["trade_number"], first["detail_url"]) == (
        "70700",
        "70700-ОТПП",
        TRADE_URL,
    )
    assert (first["status"], first["bidding_date"]) == ("Прием заявок", "04.11.2026 10:00")


async def test_следующая_страница_это_get_pagenum() -> None:
    requests = await run(crawler().parse, NISTP, URL)
    (pager,) = [r for r in requests if "trade" not in r.metadata]
    assert (pager.url, pager.metadata) == (f"{URL}?pagenum=2", {"page": 2})
    assert pager.method == "GET"


async def test_окно_по_дате_по_сроку_из_листинга() -> None:
    # Самый поздний срок на странице — в 2027 году: окно с 2028-го её закрывает.
    assert not [
        r for r in await run(crawler(since="2028-01-01").parse, NISTP, URL) if "trade" not in r.metadata
    ]


def test_путь_листинга_площадки() -> None:
    assert Sistematorg.start_urls == ["https://sistematorg.com/tradelist.php"]


async def test_лоты_торгов() -> None:
    trade = parse_listing(Selector(NISTP))[0]
    lots = await run(crawler().parse_trade, TRADE, TRADE_URL, trade=trade)
    assert [lot["lot_id"] for lot in lots] == [
        "70700_1",
        "70700_4",
        "70700_7",
    ]  # номера лотов на площадке такие
    lot = lots[0]
    assert (lot["price"], lot["status"], lot["status_raw"]) == (21434427.98, "Приём заявок", "Прием заявок")
    assert (lot["organizer"], lot["debtor"]) == ("Александров Игорь Олегович", "Вейс Андрей Эдгарович")
    assert lot["description"] == "Земельные участки в количестве 10 единиц"
    assert lot["bidding_date_raw"] == "04.11.2026 10:00:00"
    # Дата торгов — не начало приёма заявок, как клал coll-temp; у публичного
    # предложения её нет вовсе.
    assert lot["result_date"] is None
    assert lot["url"] == TRADE_URL and lot["validation"]["ok"] is True
