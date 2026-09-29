"""Детальный парсер Kendo-ETP: страница торгов -> сведения о торгах и документы.

Какие лоты обходить, решает база (``MongoStorage.pending_detail``). Детали у
Kendo — на странице торгов, общие для всех её лотов: пары ``#main-info`` и
документы ``#documents``. Страница запрашивается один раз на торги, детали
получает каждый ожидающий лот этих торгов.

Как и у iTender, детальный парсер — примесь к классу площадки: ``detail_of(Seltim)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from core.help import clean
from tp.kendo.base import Kendo, parse_main_info


def parse_documents(page: Selector) -> list[dict[str, Any]]:
    """Документы торгов: имя и ссылка из ``#documents``."""
    documents = []
    for row in page.xpath('//div[@id="documents"]//div[contains(@class, "file-row")]'):
        link = row.xpath('.//a[starts-with(@href, "http")][1]')
        if url := link.xpath("./@href").get():
            documents.append({"name": clean(link.xpath("string(.)").get()), "url": url})
    return documents


def parse_detail(page: Selector) -> dict[str, Any]:
    """Детали торгов: пары «подпись: значение» и ``attachments``."""
    return {**parse_main_info(page), "attachments": parse_documents(page)}


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class KendoDetail(Kendo):
    """Примесь: вместо листинга — страницы торгов лотов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            yield self.request(url, metadata = {"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        detail = parse_detail(response.selector())
        # Без #main-info это не страница торгов (заглушка, ошибка, переезд):
        # записать её значило бы убрать лоты из очереди с пустыми деталями.
        if detail.keys() == {"attachments"}:
            raise ValueError(f"нет сведений о торгах (#main-info) на {response.request.url}")
        for lot_id in response.metadata["lot_ids"]:
            yield {"lot_id": lot_id, "detail": detail}


def detail_of(platform: type[Kendo]) -> type[KendoDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы торгов."""
    return type(f"{platform.__name__} Detail", (KendoDetail, platform), {"__module__": platform.__module__})
