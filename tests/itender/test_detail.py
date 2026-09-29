"""Детали iTender: разделы страницы лота, пропуск служебных разделов, поток детального краулера."""

from __future__ import annotations

import pytest
from collector import Request

from tests.conftest import TESTS, Sink, collect, make, page, read_fixture, respond
from tp.itender.detail import detail_of, parse_detail
from tp.itender.source import Centerr

LOTS = sorted(p.name for p in (TESTS / "itender/fixtures").glob("lot_*.html"))
CENTERR_LOT = "itender/fixtures/lot_centerr_1170194.html"
D = detail_of(Centerr)


def test_фикстуры_на_месте() -> None:
    assert len(LOTS) == 6


@pytest.mark.parametrize("name", LOTS)
def test_разделы_всех_фикстур(name: str) -> None:
    detail = parse_detail(page(f"itender/fixtures/{name}"))
    assert "Информация о лоте" in detail
    assert "Информация о документе" not in detail
    assert isinstance(detail["Информация о лоте"]["Классификатор ЕФРСБ"], list)


def test_значения_centerr() -> None:
    detail = parse_detail(page(CENTERR_LOT))
    assert list(detail) == ["Информация о публичном предложении", "Информация о лоте", "Обеспечение заявки"]
    lot = detail["Информация о лоте"]
    assert lot["Номер"] == "1"
    assert lot["Дата начала первого интервала"] == "23.09.2026 00:00"


def test_цена_без_кнопки_агента() -> None:
    for name in LOTS:
        for section in parse_detail(page(f"itender/fixtures/{name}")).values():
            for value in section.values():
                texts = value if isinstance(value, list) else [value]
                assert all("Купить с агентом" not in (t or "") for t in texts), name


LOT_ROWS = [{"lot_id": "1", "lot_url": "https://x/1"}, {"lot_id": "2", "lot_url": "https://x/2"}]


async def test_start_requests_из_хранилища() -> None:
    d = make(D, sink=Sink(LOT_ROWS))
    reqs = [r async for r in d.start_requests()]
    assert [r.url for r in reqs] == ["https://x/1", "https://x/2"]
    assert [r.metadata for r in reqs] == [{"lot_id": "1"}, {"lot_id": "2"}]


async def test_limit() -> None:
    d = make(D, params={"limit": 1}, sink=Sink(LOT_ROWS))
    assert len([r async for r in d.start_requests()]) == 1


async def test_parse_отдаёт_детали() -> None:
    d = make(D)
    req = Request(url="https://x/1", metadata={"lot_id": "1"})
    requests, items = await collect(d.parse(respond(d, req, read_fixture(CENTERR_LOT))))
    assert requests == []
    assert items == [{"lot_id": "1", "detail": parse_detail(page(CENTERR_LOT))}]


def test_detail_of() -> None:
    assert D.name == "centerr"
    assert D.__module__ == Centerr.__module__
    assert D.params.limit == 100
    assert D.__mro__[1].__name__ == "ITenderDetail"
