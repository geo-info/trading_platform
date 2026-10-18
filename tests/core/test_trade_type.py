"""Регрессии явных названий, кодов и независимых признаков торгов."""

import pytest
from collector import Request
from parsel import Selector

from core.trade_type import normalize_trade_type, number_type, resolve_trade_type
from tests.conftest import collect, make, page, read_fixture, respond
from tp.btorg.base import parse_general, parse_listing
from tp.btorg.detail import detail_of
from tp.btorg.source import Ausib
from tp.kendo.base import parse_lots as kendo_lots
from tp.ruson.base import parse_lots as ruson_lots


@pytest.mark.parametrize("code", ["ППК", "КТПП", "КАОФ", "НЕИЗВЕСТНО"])
def test_unknown_codes(code):
    result = normalize_trade_type(code)
    assert result["trade_type"] == result["trade_type_raw"] == result["trade_type_code"] == code
    assert result["trade_kind"] is None


@pytest.mark.parametrize(
    "number,kind",
    [
        ("16539-ОТПП-К", "публичное предложение"),
        ("16324-ОТПП-К", "публичное предложение"),
        ("16238-ОАОФ-К", "аукцион"),
    ],
)
def test_ausib_extra_suffix(number, kind):
    html = f'<table class="data"><tr onclick="general.html?id=1"><td>{number}</td><td>O</td><td>D</td><td>S</td><td></td></tr></table>'
    (trade,) = parse_listing(Selector(html))
    assert trade["trade_type_raw"] == number_type(number)
    assert trade["trade_type_code"].endswith("-К")
    assert trade["trade_kind"] == kind


def test_price_form_is_not_participation():
    result = normalize_trade_type("Аукцион с закрытой формой представления цены")
    assert result["trade_participation"] is None
    assert result["trade_price_form"] == "закрытая"
    result = normalize_trade_type("Закрытый конкурс с открытой формой представления цены")
    assert result["trade_participation"] == "закрытая"
    assert result["trade_price_form"] == "открытая"


def test_page_wins_conflicting_code():
    result = resolve_trade_type({"Тип торгов": "Публичное предложение"}, {"trade_number": "1-ОАОФ"})
    assert result["trade_kind"] == "публичное предложение"
    assert result["trade_price_form"] is None
    assert result["trade_type_code"] == "ОАОФ"


def test_plain_page_code_does_not_replace_explicit_title():
    title = "Открытый аукцион с открытой формой представления предложений о цене (Банкротство)"
    result = resolve_trade_type({"Номер торгов": "1-ОАОФ"}, {"trade_type": title})
    assert result["trade_type"] == result["trade_type_raw"] == title
    assert result["trade_type_code"] == "ОАОФ"


def test_ausib_public_offer_general():
    info = parse_general(page("btorg/fixtures/general_ausib_16539.html"))
    result = resolve_trade_type(info, {"trade_number": "16539-ОТПП-К"})
    assert result["trade_type"] == "Открытые торги посредством публичного предложения (ГК РФ)"
    assert result["trade_kind"] == "публичное предложение"
    assert result["trade_participation"] == "открытая"
    assert result["trade_price_form"] is None
    assert result["trade_type_code"] == "ОТПП-К"


@pytest.mark.parametrize("fixture", ["trade_496200.html", "trade_el_torg_113964.html"])
def test_ruson_explicit_type(fixture):
    lots = ruson_lots(page(f"ruson/fixtures/{fixture}"), {"trade_id": "1", "trade_type": "ОАОФ"})
    assert lots
    assert all(lot["trade_type"] == "Публичное предложение" for lot in lots)


def test_kendo_expanded_number():
    html = read_fixture("kendo/fixtures/trade_10840.html")
    html = html.replace(
        "10840–ОАОФ", "10840–ОАОФ (Открытый аукцион с открытой формой представления предложений о цене)"
    )
    (lot,) = kendo_lots(Selector(html), {"trade_id": "10840", "trade_type": "ОТПП"})
    assert lot["trade_kind"] == "аукцион"
    assert lot["trade_type_source"] == "page:Номер торгов"
    assert lot["trade_type_code"] == "ОАОФ"


async def test_ausib_explicit_page_then_fragment():
    crawler = make(Ausib)
    req = Request(
        url="https://ausib.ru/trade/view/purchase/general.html?id=104661680",
        metadata={
            "trade": {
                "trade_id": "1",
                "trade_number": "1-ОАОФ",
                "trade_type": "ОАОФ",
                "page_url": "/trade/view/purchase/general.html?id=104661680",
                "trade_url": "/etp/trade/inner-view-lots.html?id=104661680",
            }
        },
    )
    fixture = "btorg/fixtures/general_ausib_104661680.html"
    (fragment,), _ = await collect(crawler.parse_general(respond(crawler, req, read_fixture(fixture))))
    assert fragment.headers["X-Requested-With"] == "XMLHttpRequest"
    _, (lot,) = await collect(
        crawler.parse_trade(
            respond(crawler, fragment, read_fixture("btorg/fixtures/lots_13147.html", "cp1251"))
        )
    )
    assert (
        lot["trade_type"]
        == "Открытый аукцион с открытой формой представления предложений о цене (Банкротство)"
    )
    assert lot["trade_type_code"] == "ОАОФ"
    assert lot["trade_participation"] == lot["trade_price_form"] == "открытая"
    assert (
        parse_general(page(fixture))["Форма проведения торгов и подачи предложений"] == lot["trade_type_raw"]
    )


async def test_btorg_detail_keeps_general():
    crawler = make(detail_of(Ausib))
    req = Request(
        url="https://ausib.ru/general", metadata={"lot_ids": ["1_1"], "lots_url": "https://ausib.ru/lots"}
    )
    (fragment,), _ = await collect(
        crawler.parse_general_detail(
            respond(crawler, req, read_fixture("btorg/fixtures/general_ausib_104661680.html"))
        )
    )
    _, (item,) = await collect(
        crawler.parse(respond(crawler, fragment, read_fixture("btorg/fixtures/lots_13147.html", "cp1251")))
    )
    assert "Форма проведения торгов и подачи предложений" in item["detail"]["trade_info"]
