"""Детальный парсер Kendo-ETP: страница торгов -> разделы с парами «подпись: значение».

Какие лоты обходить, решает база (``Store.pending_detail``). Всё о лоте —
на странице торгов: сведения о торгах, карточка лота и документы. Страница
у лотов одних торгов общая, поэтому запрос на торги один, а деталей — по
числу её лотов, ждущих деталей (см. ``tp.common.TradeDetail``).

Детальный парсер — примесь к классу площадки: ``detail_of(TradeAlliance)``.
"""

from __future__ import annotations

from typing import Any

from parsel import Selector

from core.help import clean
from tp.common import TradeDetail
from tp.common import detail_of as _detail_of
from tp.kendo.base import Kendo, lot_blocks, lot_link, lot_price, lot_status, parse_main_info


def parse_documents(page: Selector) -> list[dict[str, Any]]:
    """Документы торгов: имя и ссылка из ``#documents``."""
    documents = []
    for row in page.xpath('//div[@id="documents"]//div[contains(@class, "file-row")]'):
        link = row.xpath('.//a[starts-with(@href, "http")][1]')
        if url := link.xpath("./@href").get():
            documents.append({"name": clean(link.xpath("string(.)").get()), "url": url})
    return documents


def parse_lot(block: Selector) -> dict[str, str | None]:
    """Карточка лота: наименование, цена, статус и строки «подпись: значение»."""
    pairs: dict[str, str | None] = {
        "Наименование": clean(lot_link(block).xpath("string(.)").get()),
        "Начальная цена": lot_price(block),
        "Статус лота": lot_status(block),
    }
    for row in block.xpath('.//div[contains(@class, "grey-text")]'):
        label, sep, value = (clean(row.xpath("string(.)").get()) or "").partition(":")
        if sep and label.strip() and label.strip() not in pairs:
            pairs[label.strip()] = clean(value)
    return pairs


def parse_detail(page: Selector, lot_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Детали лотов ``lot_ids`` (``<торги>_<номер лота>``) со страницы торгов."""
    shared = {"Сведения о торгах": parse_main_info(page), "Документы": parse_documents(page)}
    blocks = dict(lot_blocks(page))
    details = {}
    for lot_id in lot_ids:
        block = blocks.get(lot_id.rsplit("_", 1)[-1])
        if block is not None:
            details[lot_id] = {"Лот": parse_lot(block), **shared}
    return details


class KendoDetail(TradeDetail):
    """Примесь: вместо листинга — страницы торгов лотов, ждущих деталей."""

    parse_detail = staticmethod(parse_detail)


def detail_of(platform: type[Kendo]) -> type[KendoDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы торгов."""
    return _detail_of(platform, KendoDetail)
