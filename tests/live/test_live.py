"""Живые тесты: площадки по-настоящему, по одной на движок. Не в CI.

    uv run pytest -m live

Нужна сеть до площадок (с VPN — исключения для их адресов). Хранилище не
нужно: детали берутся по лотам, собранным листингом в этом же тесте.
"""

from __future__ import annotations

import pytest
from collector import open_crawl

from core.lot import Lot
from tests.conftest import Sink
from tp.btorg.detail import detail_of as btorg_detail
from tp.itender.detail import detail_of as itender_detail
from tp.kendo.detail import detail_of as kendo_detail
from tp.platforms import platforms
from tp.ruson.detail import detail_of as ruson_detail

pytestmark = pytest.mark.live

CASES = {
    "centerr": itender_detail,
    "trade_alliance": kendo_detail,
    "atctrade": btorg_detail,
    "rus_on": ruson_detail,
}


@pytest.mark.parametrize("name", list(CASES))
async def test_площадка_живая(name: str) -> None:
    platform = platforms()[name]
    async with open_crawl(platform, params={"max_pages": 1}) as crawl:
        lots = [item async for item in crawl.stream()]
    assert lots, f"{name}: листинг не дал ни одного лота ({crawl.stats.reason})"
    assert crawl.stats.errors == 0
    Lot.model_validate({k: v for k, v in lots[0].items() if k in Lot.model_fields})

    detail = CASES[name](platform)
    async with open_crawl(detail, params={"limit": 1}, sink=Sink(lots)) as crawl:
        details = [item async for item in crawl.stream()]
    assert crawl.stats.errors == 0
    assert details and details[0]["detail"], f"{name}: детали пустые"
