"""Детальный парсер rus-on: страница торгов -> разделы с парами «подпись: значение».

Какие лоты обходить, решает база (``Store.pending_detail``). Своей страницы у
лота нет — всё о нём на странице торгов, общей для лотов одних торгов: запрос
на торги один, а деталей — по числу её лотов, ждущих деталей (см.
``tp.common.TradeDetail``).

Детальный парсер — примесь к классу площадки: ``detail_of(Nistp)``.
"""

from __future__ import annotations

from typing import Any

from parsel import Selector

from tp.common import TradeDetail
from tp.common import detail_of as _detail_of
from tp.ruson.base import Ruson, block, lot_tables, pairs_of

#: Разделы страницы торгов, общие для всех её лотов: заголовок на странице -> раздел деталей.
SECTIONS = {
    "Информация о должнике": "Должник",
    "Информация об организаторе": "Организатор",
    "Контактное лицо организатора": "Контактное лицо организатора",
}


def parse_detail(page: Selector, lot_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Детали лотов ``lot_ids`` (``<торги>_<номер лота>``) со страницы торгов."""
    shared = {name: pairs_of(table) for title, name in SECTIONS.items() if (table := block(page, title))}
    tables = {lot_num: table for lot_num, _, table in lot_tables(page)}
    details = {}
    for lot_id in lot_ids:
        table = tables.get(lot_id.rsplit("_", 1)[-1])
        if table is not None:
            details[lot_id] = {"Лот": pairs_of(table), **shared}
    return details


class RusonDetail(TradeDetail):
    """Примесь: вместо листинга — страницы торгов лотов, ждущих деталей."""

    parse_detail = staticmethod(parse_detail)


def detail_of(platform: type[Ruson]) -> type[RusonDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы торгов."""
    return _detail_of(platform, RusonDetail)
