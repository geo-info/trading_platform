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

from tp.btorg.base import XHR, Btorg, lot_pairs, lot_tables, parse_general, parse_schedule


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
        limit = self.params.limit
        lots = [lot async for lot in self.ctx.sink.pending_detail(limit + 1 if limit else 0)]
        self.limit_reached = bool(limit and len(lots) > limit)
        lots = lots[: limit or None]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            purchase = url.split("id=", 1)[-1].split("&", 1)[0]
            general_url = f"{self.DOMAIN}/trade/view/purchase/general.html?id={purchase}"
            yield self.request(
                general_url,
                callback=self.parse_general_detail,
                metadata={"lot_ids": lot_ids, "lots_url": url},
            )

    async def parse_general_detail(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        yield self.request(
            response.metadata["lots_url"],
            headers=XHR,
            metadata={"lot_ids": response.metadata["lot_ids"], "general": parse_general(response.selector())},
        )

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        details = parse_details(response.selector())
        # Ни одного лота — это не торги, а заглушка, ошибка или переезд: отметить
        # все лоты «сняты» значило бы убрать их из очереди без деталей.
        if not details:
            raise ValueError(f"нет таблиц лотов во фрагменте {response.request.url}")
        for lot_id in response.metadata["lot_ids"]:
            # lot_id — «{trade_id}_{lot_num}», trade_id — одни цифры.
            lot_num = lot_id.partition("_")[2]
            if lot_num not in details:
                # Лот сняли с торгов: detail=None — хранилище отметит, что
                # страницу смотрели, и лот не будет перечитываться вечно.
                await self.log(f"лота {lot_id} во фрагменте нет — отмечаю без деталей")
            detail = details.get(lot_num)
            if detail is not None and response.metadata.get("general"):
                detail = {**detail, "trade_info": response.metadata["general"]}
            yield {"lot_id": lot_id, "detail": detail}


def detail_of(platform: type[Btorg]) -> type[BtorgDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — фрагменты лотов."""
    return type(f"{platform.__name__} Detail", (BtorgDetail, platform), {"__module__": platform.__module__})
