"""Детальный парсер btorg: фрагмент лотов -> пары таблицы лота и график снижения цены.

Какие лоты обходить, решает база (``MongoStorage.pending_detail``). Детали —
во фрагменте ``inner-view-lots.html`` торгов, по таблице на лот. Фрагмент
запрашивается один раз на торги (с признаком XHR), каждый ожидающий лот
получает свою таблицу.

Как и у iTender, детальный парсер — примесь к классу площадки: ``detail_of(Atctrade)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from tp.btorg.base import XHR, Btorg, lot_pairs, lot_tables, parse_schedule


def parse_details(page: Selector) -> dict[str, dict[str, Any]]:
    """Детали каждого лота фрагмента: номер лота -> пары и ``price_schedule``."""
    return {
        lot_num: {**lot_pairs(table), "price_schedule": parse_schedule(table)}
        for lot_num, table in lot_tables(page)
    }


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class BtorgDetail(Btorg):
    """Примесь: вместо листинга — фрагменты лотов торгов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            yield self.request(url, headers = XHR, metadata = {"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        details = parse_details(response.selector())
        for lot_id in response.metadata["lot_ids"]:
            # lot_id — «{trade_id}_{lot_num}», trade_id — одни цифры.
            lot_num = lot_id.partition("_")[2]
            if lot_num in details:
                yield {"lot_id": lot_id, "detail": details[lot_num]}
            else:
                await self.log(f"лота {lot_id} во фрагменте нет — детали не записаны")


def detail_of(platform: type[Btorg]) -> type[BtorgDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — фрагменты лотов."""
    return type(f"{platform.__name__} Detail", (BtorgDetail, platform), {"__module__": platform.__module__})
