"""Детали rus-on: пары таблицы каждого лота, график снижения цены, группировка по торгам, пропавший лот, класс детального парсера."""

from __future__ import annotations

import pytest
from collector import Request
from parsel import Selector

from core.help import parse_datetime
from tests.conftest import Sink, collect, make, page, read_fixture, respond
from tp.ruson.base import Ruson
from tp.ruson.detail import RusonDetail, detail_of, parse_details
from tp.ruson.source import Nistp

TRADE = "ruson/fixtures/trade_496200.html"
D = detail_of(Nistp)
URL = "https://nistp.ru/bankrot/trade_view.php?trade_nid=496200"


def test_parse_details() -> None:
    details = parse_details(page(TRADE))
    assert set(details) == {"1", "4", "7"}
    # 11 пар своей таблицы лота + график; строки вложенной таблицы интервалов — не пары.
    assert all(len(pairs) == 12 for pairs in details.values())
    assert details["1"]["Номер лота"] == "1"
    assert details["1"]["Наименование имущества"] == "Земельные участки в количестве 10 единиц"
    assert details["1"]["Начальная цена"] == "21 434 427.98"
    assert details["7"]["Номер лота"] == "7"
    assert details["7"]["Местонахождение имущества"] == "Самарская область, сельское поселение Красный Яр"
    assert details["7"]["Начальная цена"] == "628 176.38"
    assert details["4"]["Начальная цена"] == "267 690.47"


def test_строки_графика_не_попадают_в_пары() -> None:
    """Строки вложенной таблицы интервалов давали пары «дата начала: дата окончания»,
    а сама строка «Интервалы снижения цены» — склеенный текст всей таблицы."""
    for pairs in parse_details(page(TRADE)).values():
        labels = [label for label in pairs if label != "price_schedule"]
        assert [label for label in labels if parse_datetime(label)] == []
        assert "Интервалы снижения цены" not in pairs


def test_график_снижения_цены() -> None:
    details = parse_details(page(TRADE))
    schedule = details["1"]["price_schedule"]
    assert len(schedule) == 5
    assert schedule[0] == {
        "Дата начала интервала": "27.09.2026 10:00",
        "Дата окончания интервала": "07.10.2026 09:59",
        "Цена на интервале, руб.": "21 434 427.98",
        "Размер задатка, руб.": "2 143 442.80",
    }
    assert schedule[-1]["Дата окончания интервала"] == "04.11.2026 10:00"
    assert details["4"]["price_schedule"][0]["Цена на интервале, руб."] == "267 690.47"


def test_лот_без_графика() -> None:
    html = (
        "<table><tr><th>Лот № 1</th></tr>"
        "<tr><td>Наименование имущества</td><td>Квартира</td></tr>"
        "<tr><td>Начальная цена</td><td>1 000.00</td></tr></table>"
    )
    assert parse_details(Selector(html)) == {
        "1": {"Наименование имущества": "Квартира", "Начальная цена": "1 000.00", "price_schedule": []}
    }


async def test_start_requests_группирует() -> None:
    sink = Sink(
        [
            {"lot_id": "496200_1", "lot_url": "u1", "trade_url": "https://t/496200"},
            {"lot_id": "496200_4", "lot_url": "u2", "trade_url": "https://t/496200"},
            {"lot_id": "5_1", "lot_url": "https://t/5"},
        ]
    )
    d = make(D, sink=sink)
    reqs = [r async for r in d.start_requests()]
    assert [r.url for r in reqs] == ["https://t/496200", "https://t/5"]
    assert [r.metadata for r in reqs] == [{"lot_ids": ["496200_1", "496200_4"]}, {"lot_ids": ["5_1"]}]


async def test_parse_детали_по_номеру_лота() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["496200_1", "496200_4"]})
    requests, items = await collect(d.parse(respond(d, req, read_fixture(TRADE))))
    details = parse_details(page(TRADE))
    assert requests == []
    assert [i["lot_id"] for i in items] == ["496200_1", "496200_4"]
    assert items[0]["detail"] == details["1"]
    assert items[1]["detail"] == details["4"]
    assert items[0]["detail"]["Начальная цена"] == "21 434 427.98"
    assert items[1]["detail"]["Начальная цена"] == "267 690.47"
    assert items[1]["detail"]["Номер лота"] == "4"


async def test_пропавший_лот_detail_none() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["496200_1", "496200_99"]})
    _, items = await collect(d.parse(respond(d, req, read_fixture(TRADE))))
    assert [i["lot_id"] for i in items] == ["496200_1", "496200_99"]
    assert items[0]["detail"] is not None
    assert items[1]["detail"] is None


async def test_страница_без_лотов_ошибка() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["1_1"]})
    with pytest.raises(ValueError, match="нет лотов"):
        await collect(d.parse(respond(d, req, "<html><body>заглушка</body></html>")))


def test_detail_of() -> None:
    assert D.name == "nistp"
    assert D.__module__ == Nistp.__module__
    assert D.params.limit == 100
    assert D.__mro__[1:4] == (RusonDetail, Nistp, Ruson)
