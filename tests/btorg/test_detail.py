"""Детали btorg: пары таблицы лота и график снижения цены, группировка по торгам, XHR, пропавший лот."""

from __future__ import annotations

from collector import Request

from tests.conftest import Sink, collect, make, page, read_fixture, respond
from tp.btorg.detail import detail_of, parse_details
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
    assert item["detail"] == parse_details(page(LOTS, ENC))["1"]


async def test_пропавший_лот_detail_none() -> None:
    d = make(D)
    req = Request(url=URL, metadata={"lot_ids": ["13147_1", "13147_99"]})
    _, items = await collect(d.parse(respond(d, req, read_fixture(LOTS, ENC))))
    assert [i["lot_id"] for i in items] == ["13147_1", "13147_99"]
    assert items[0]["detail"] is not None
    assert items[1]["detail"] is None


def test_detail_of() -> None:
    assert D.name == "atctrade"
    assert D.__module__ == Atctrade.__module__
    assert D.params.limit == 100
    assert [c.__name__ for c in D.__mro__[:4]] == [
        "Atctrade Detail",
        "BtorgDetail",
        "Atctrade",
        "Btorg",
    ]
