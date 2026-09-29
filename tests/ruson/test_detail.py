"""Детали rus-on: пары таблицы каждого лота, группировка по торгам, пропавший лот, класс детального парсера."""

from __future__ import annotations

from collector import Request

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
    assert all(len(pairs) == 17 for pairs in details.values())
    assert details["1"]["Номер лота"] == "1"
    assert details["1"]["Наименование имущества"] == "Земельные участки в количестве 10 единиц"
    assert details["1"]["Начальная цена"] == "21 434 427.98"
    assert details["7"]["Номер лота"] == "7"
    assert details["7"]["Местонахождение имущества"] == "Самарская область, сельское поселение Красный Яр"
    assert details["7"]["Начальная цена"] == "628 176.38"
    assert details["4"]["Начальная цена"] == "267 690.47"


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


def test_detail_of() -> None:
    assert D.name == "nistp"
    assert D.__module__ == Nistp.__module__
    assert D.params.limit == 100
    assert D.__mro__[1:4] == (RusonDetail, Nistp, Ruson)
