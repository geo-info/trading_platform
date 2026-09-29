"""Детальный парсер rus-on: страница торгов -> пары таблицы лота.

Какие лоты обходить, решает база (``MongoStorage.pending_detail``). Детали —
на странице торгов, по таблице «Лот № N» на лот. Страница запрашивается один
раз на торги, каждый ожидающий лот получает свою таблицу.

Как и у iTender, детальный парсер — примесь к классу площадки: ``detail_of(Nistp)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from tp.ruson.base import Ruson, lot_pairs, lot_tables


def parse_details(page: Selector) -> dict[str, dict[str, Any]]:
    """Детали каждого лота страницы торгов: номер лота -> пары его таблицы."""
    return {lot_num: lot_pairs(table) for lot_num, _, table in lot_tables(page)}


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class RusonDetail(Ruson):
    """Примесь: вместо листинга — страницы торгов лотов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            yield self.request(url, metadata={"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        details = parse_details(response.selector())
        for lot_id in response.metadata["lot_ids"]:
            # lot_id — «{trade_id}_{lot_num}», trade_id — одни цифры.
            lot_num = lot_id.partition("_")[2]
            if lot_num not in details:
                # Лот сняли с торгов: detail=None — хранилище отметит, что
                # страницу смотрели, и лот не будет перечитываться вечно.
                await self.log(f"лота {lot_id} на странице торгов нет — отмечаю без деталей")
            yield {"lot_id": lot_id, "detail": details.get(lot_num)}


def detail_of(platform: type[Ruson]) -> type[RusonDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы торгов."""
    return type(f"{platform.__name__} Detail", (RusonDetail, platform), {"__module__": platform.__module__})
