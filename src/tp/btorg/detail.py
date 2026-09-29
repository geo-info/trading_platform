"""Детальный парсер btorg: фрагмент лотов торгов -> пары «подпись: значение» и график цены.

Какие лоты обходить, решает база (``Store.pending_detail``). Своей страницы у
лота нет — всё о нём во фрагменте лотов торгов (``trade_url``), общем для
лотов одних торгов: запрос на торги один, а деталей — по числу её лотов,
ждущих деталей (см. ``tp.common.TradeDetail``). Фрагмент отдаётся только на
AJAX-запрос.

Детальный парсер — примесь к классу площадки: ``detail_of(Atctrade)``.
"""

from __future__ import annotations

from typing import Any

from parsel import Selector

from tp.btorg.base import XHR, Btorg, lot_pairs, lot_tables, parse_schedule
from tp.common import TradeDetail
from tp.common import detail_of as _detail_of


def parse_detail(page: Selector, lot_ids: list[str]) -> dict[str, dict[str, Any]]:
    """Детали лотов ``lot_ids`` (``<торги>_<номер лота>``) из фрагмента лотов."""
    tables = dict(lot_tables(page))
    details = {}
    for lot_id in lot_ids:
        table = tables.get(lot_id.rsplit("_", 1)[-1])
        if table is not None:
            details[lot_id] = {"Лот": lot_pairs(table), "График снижения цены": parse_schedule(table)}
    return details


class BtorgDetail(TradeDetail):
    """Примесь: вместо листинга — фрагменты лотов торгов, ждущих деталей."""

    DETAIL_HEADERS = XHR

    parse_detail = staticmethod(parse_detail)


def detail_of(platform: type[Btorg]) -> type[BtorgDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — фрагмента лотов."""
    return _detail_of(platform, BtorgDetail)
