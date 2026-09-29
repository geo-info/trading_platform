"""Детали btorg: пары таблицы лота и график снижения цены, группировка по торгам, XHR, пропавший лот."""

from __future__ import annotations

import pytest
from collector import Request

from tests.conftest import Sink, collect, make, page, read_fixture, respond
from tp.btorg.base import Btorg
from tp.btorg.detail import BtorgDetail, detail_of, parse_details
from tp.btorg.source import Atctrade

LOTS = "btorg/fixtures/lots_13147.html"
ENC = "cp1251"
D = detail_of(Atctrade)
URL = "https://atctrade.ru/etp/trade/inner-view-lots.html?perspective=inline&id=105491777"


def test_parse_details() -> None:
    details = parse_details(page(LOTS, ENC))
    assert list(details) == ["1"]
    detail = details["1"]
    schedule = detail.pop("price_schedule")
    assert len(detail) == 6
    assert len(schedule) == 5
    assert all("Дата окончания приема заявок" in interval for interval in schedule)
    assert detail["Предмет торгов"] == "Транспортное средство"
    assert detail["Классификатор имущества"] == "0106008. Автомобили"
    assert detail["Начальная цена продажи имущества"] == "333 000,00 руб, НДС не облагается"
    assert schedule[0] == {
        "Дата начала приема заявок": "28.09.2026 08:00",
        "Дата окончания приема заявок": "02.10.2026 17:00",
        "Цена на периоде, руб.": "333 000,00",
        "Размер задатка, руб.": "33 300,00",
    }
    assert schedule[-1]["Дата окончания приема заявок"] == "22.10.2026 17:00"


async def test_start_requests_группирует_и_xhr() -> None:
    sink = Sink(
        [
            {"lot_id": "13147_1", "lot_url": "u1", "trade_url": "https://t/13147"},
            {"lot_id": "13147_2", "lot_url": "u2", "trade_url": "https://t/13147"},
            {"lot_id": "5_1", "lot_url": "https://t/5"},
        ]
    )
    d = make(D, sink=sink)
    reqs = [r async for r in d.start_requests()]
    assert [r.url for r in reqs] == ["https://t/13147", "https://t/5"]
    assert [r.metadata for r in reqs] == [{"lot_ids": ["13147_1", "13147_2"]}, {"lot_ids": ["5_1"]}]
    assert all(r.headers["X-Requested-With"] == "XMLHttpRequest" for r in reqs)


async def test_parse_детали_по_номеру_лота() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["13147_1"]})
    requests, items = await collect(d.parse(respond(d, req, read_fixture(LOTS, ENC))))
    assert requests == []
    (item,) = items
    assert item["lot_id"] == "13147_1"
    assert item["detail"]["Предмет торгов"] == "Транспортное средство"
    assert item["detail"]["price_schedule"][-1]["Дата окончания приема заявок"] == "22.10.2026 17:00"


async def test_пропавший_лот_detail_none() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["13147_1", "13147_99"]})
    _, items = await collect(d.parse(respond(d, req, read_fixture(LOTS, ENC))))
    assert [i["lot_id"] for i in items] == ["13147_1", "13147_99"]
    assert items[0]["detail"] is not None
    assert items[1]["detail"] is None


async def test_страница_без_лотов_ошибка() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["1_1"]})
    with pytest.raises(ValueError, match="таблиц лотов"):
        await collect(d.parse(respond(d, req, "<html><body>заглушка</body></html>")))


def test_detail_of() -> None:
    assert D.name == "atctrade"
    assert D.__module__ == Atctrade.__module__
    assert D.params.limit == 100
    assert D.__mro__[1:4] == (BtorgDetail, Atctrade, Btorg)
