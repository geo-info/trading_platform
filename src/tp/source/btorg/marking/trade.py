"""Разметка фрагмента лотов торгов btorg: ``inner-view-lots.html``.

По ``table.data`` на лот (``id="lotNumberN"``) с парами «подпись — значение»
и, у публичного предложения, вложенной таблицей интервалов снижения цены.
Исправлено против coll-temp: срок приёма — конец последнего интервала, а не
начало приёма из листинга; интервалы — в ``price_schedule``, а не датами-
подписями в ``extra``.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean, parse_price

_LOT_NUM_RE = re.compile(r"lotNumber(\d+)")


def property_details(detail: dict[str, str]) -> str | None:
    """«Сведения об имуществе должника…» — описание лота, где «Предмет торгов» не заполнен.

    Ищется по вхождению: первая «С» в подписи на части площадок латинская.
    """
    return next((value for label, value in detail.items() if "ведения об имуществе" in label), None)


def parse_schedule(lot: Selector) -> list[dict[str, str]]:
    """Интервалы снижения цены публичного предложения: строка -> {заголовок: ячейка}."""
    table = lot.xpath('.//table[contains(@class, "inner")]')
    headers = [clean(td.xpath("string(.)").get()) or "" for td in table.xpath(".//tr[1]/*")]
    schedule: list[dict[str, str]] = []
    for row in table.xpath(".//tr[position() > 1]"):
        cells = [clean(td.xpath("string(.)").get()) or "" for td in row.xpath("./td")]
        if headers and len(cells) == len(headers):
            schedule.append(dict(zip(headers, cells, strict=True)))
    return schedule


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Таблицы ``lotNumberN`` фрагмента -> лоты; сведения о торгах — из листинга."""
    lots: list[dict[str, Any]] = []
    for lot in page.xpath('//table[contains(@id, "lotNumber")]'):
        lot_num = _LOT_NUM_RE.search(lot.xpath("./@id").get() or "")
        # Только свои строки таблицы лота — строки вложенной таблицы интервалов
        # дали бы в extra подписи-даты.
        own_rows = lot.xpath(".//tr[td[2]][ancestor::table[1][contains(@id, 'lotNumber')]]")
        detail = {
            label.rstrip(":").strip(): value
            for row in own_rows
            if (label := clean(row.xpath("string(./td[1])").get()))
            and (value := clean(row.xpath("string(./td[2])").get()))
        }
        schedule = parse_schedule(lot)
        price_raw = detail.get("Начальная цена продажи имущества")
        lots.append(
            {
                "lot_id": f"{trade['trade_id']}_{lot_num.group(1)}" if lot_num else None,
                "trade_id": trade["trade_id"],
                "trade_number": trade.get("trade_number"),
                "trade_type": trade.get("trade_type"),
                "lot_num": lot_num.group(1) if lot_num else None,
                "debtor": trade.get("debtor"),
                "organizer": trade.get("organizer"),
                "lot_url": trade.get("lots_url"),
                "description": detail.get("Предмет торгов") or property_details(detail),
                "price": parse_price(price_raw),
                "price_raw": price_raw,
                "status": detail.get("Статус торгов") or trade.get("status"),
                # Срок приёма публичного предложения — конец последнего интервала.
                "bidding_date": schedule[-1].get("Дата окончания приема заявок") if schedule else None,
                "detail": {**detail, "Начало приема заявок": trade.get("bids_start")},
                "price_schedule": schedule,
            }
        )
    return lots
