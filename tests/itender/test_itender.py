"""Движок iTender на настоящих страницах: листинг centerr и страница лота 1170194.

Фикстуры — общие со старыми тестами fogsoft (``tests/fogsoft/fixtures``).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from collector import CrawlerContext

from core.lot import Lot
from tests.helpers import run
from tp.itender.base import ITender
from tp.itender.detail import detail_of
from tp.itender.source import PLATFORMS, Alfalot, Arbbitlot, Centerr, MetaInvest

FIXTURES = Path(__file__).parents[1] / "fogsoft" / "fixtures"
LISTING = (FIXTURES / "listing_centerr.html").read_text(encoding="utf-8")
LOT = (FIXTURES / "lot_centerr_1170194.html").read_text(encoding="utf-8")
URL = Centerr.start_urls[0]
LOT_URL = "https://bankrupt.centerr.ru/public/auctions/lots/view/1170194/"


def crawler(**params: Any) -> Centerr:
    return Centerr(CrawlerContext(http=None, params=params))


def test_площадки_и_их_особенности() -> None:
    assert len(PLATFORMS) == 16
    assert URL == "https://bankrupt.centerr.ru/public/purchases-all/"
    # Особенность площадки — поверх настроек движка, остальное — как у движка.
    assert (Alfalot.settings.concurrency, len(Alfalot.settings.response_hooks)) == (1, 1)
    assert Arbbitlot.settings.skip_tls_verify and MetaInvest.settings.extra_ca_cert
    assert Centerr.settings == ITender.settings
    assert Alfalot.settings.delay == ITender.settings.delay


async def test_листинг_лоты_и_следующая_страница() -> None:
    out = await run(crawler().parse, LISTING, URL)
    lots = [item for item in out if isinstance(item, dict)]
    (pager,) = [item for item in out if not isinstance(item, dict)]
    assert len(lots) == 20
    assert (lots[0]["source"], lots[0]["lot_id"]) == ("centerr", "1170229")
    assert lots[0]["lot_url"] == "https://bankrupt.centerr.ru/public/auctions/lots/view/1170229/"
    # Айтем iTender ложится в общую модель лота как есть.
    Lot(**lots[0])
    assert pager.metadata == {"num_page": 2} and pager.method == "POST"


async def test_предел_страниц() -> None:
    out = await run(crawler(max_pages="1").parse, LISTING, URL)
    assert all(isinstance(item, dict) for item in out)


async def test_детальный_парсер() -> None:
    class Sink:
        async def pending_detail(self, limit: int, statuses: list[str] | None = None) -> Any:
            assert statuses == ["Прием заявок", "Приём заявок"]
            yield {"lot_id": "1170194", "lot_url": LOT_URL}

    detail = detail_of(Centerr)
    assert (detail.name, detail.settings, detail.__module__) == ("centerr", Centerr.settings, Centerr.__module__)
    c = detail(CrawlerContext(http=None, sink=Sink(), params={"statuses": "Прием заявок, Приём заявок"}))
    (request,) = [r async for r in c.start_requests()]
    assert (request.url, request.metadata) == (LOT_URL, {"lot_ids": ["1170194"]})

    (item,) = await run(c.parse, LOT, LOT_URL, lot_ids=["1170194"])
    assert item["lot_id"] == "1170194"
    assert list(item["detail"]) == ["Информация о публичном предложении", "Информация о лоте", "Обеспечение заявки"]
