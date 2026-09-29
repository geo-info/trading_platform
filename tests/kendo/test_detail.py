"""Детали Kendo: пары main-info и документы, группировка лотов по торгам, поток детального краулера."""

from __future__ import annotations

import pytest
from collector import Request

from tests.conftest import Sink, collect, make, page, read_fixture, respond
from tp.kendo.detail import detail_of, parse_detail
from tp.kendo.source import TradeAlliance

TRADE = "kendo/fixtures/trade_10840.html"
D = detail_of(TradeAlliance)


def test_parse_detail() -> None:
    detail = parse_detail(page(TRADE))
    attachments = detail.pop("attachments")
    assert len(detail) == 26
    assert len(attachments) == 3
    assert all(a["name"] and a["url"].startswith("http") for a in attachments)


async def test_start_requests_группирует_по_trade_url() -> None:
    sink = Sink(
        [
            {"lot_id": "10840_1", "lot_url": "u1", "trade_url": "https://t/10840"},
            {"lot_id": "10840_2", "lot_url": "u2", "trade_url": "https://t/10840"},
            {"lot_id": "5_1", "lot_url": "https://t/5/lots/1"},
        ]
    )
    d = make(D, sink=sink)
    reqs = [r async for r in d.start_requests()]
    assert [r.url for r in reqs] == ["https://t/10840", "https://t/5/lots/1"]
    assert [r.metadata for r in reqs] == [{"lot_ids": ["10840_1", "10840_2"]}, {"lot_ids": ["5_1"]}]


async def test_parse_детали_каждому_лоту() -> None:
    d = make(D)
    req = Request(url="https://t/10840", metadata={"lot_ids": ["10840_1", "10840_2"]})
    requests, items = await collect(d.parse(respond(d, req, read_fixture(TRADE))))
    assert requests == []
    assert [i["lot_id"] for i in items] == ["10840_1", "10840_2"]
    assert items[0]["detail"] == items[1]["detail"] == parse_detail(page(TRADE))


async def test_страница_без_main_info_ошибка() -> None:
    d = make(D)
    req = Request(url="https://t/1", metadata={"lot_ids": ["1_1"]})
    with pytest.raises(ValueError, match="main-info"):
        await collect(d.parse(respond(d, req, "<html><body>заглушка</body></html>")))


def test_detail_of() -> None:
    assert D.name == "trade_alliance"
    assert D.__module__ == TradeAlliance.__module__
    assert D.params.limit == 100
    assert [c.__name__ for c in D.__mro__[:4]] == [
        "TradeAlliance Detail",
        "KendoDetail",
        "TradeAlliance",
        "Kendo",
    ]
