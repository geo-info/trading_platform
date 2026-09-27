"""Разметка листинга btorg (edoc-ETP): таблица торгов и пейджер.

``table.data``, строка на торги: номер, организатор, должник с предметом
торгов, состояние, начало приёма заявок. Внутренний id торгов для запроса
лотов — в ``onclick`` строки. В coll-temp организатор и должник были
перепутаны: колонка «Организатор» идёт перед «Должником».
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean

_PAGE_RE = re.compile(r"page=(\d+)")


_DIGITS_RE = re.compile(r"\d+")


_ID_RE = re.compile(r"id=(\d+)")


#: AJAX-фрагмент с лотами торгов — с ценами, которых нет в листинге.
LOTS_PATH = "/etp/trade/inner-view-lots.html"


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Строки ``table.data`` -> торги.

    Внутренний id торгов, по которому запрашиваются лоты, — в ``onclick``
    строки (``…general.html?id=NNN…``), видимого номера для этого мало.
    """
    trades: list[dict[str, Any]] = []
    for row in page.xpath('//table[@class="data"]//tr[@onclick]'):
        purchase = _ID_RE.search(row.xpath("./@onclick").get() or "")
        cells = row.xpath("./td")
        if not purchase or len(cells) < 5:
            continue
        number = clean(cells[0].xpath("string(.)").get())
        digits = _DIGITS_RE.search(number or "")
        if not number or not digits:
            continue
        parts = number.split("-")
        trades.append(
            {
                "trade_id": digits.group(0),
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "organizer": clean(cells[1].xpath("string(.)").get()),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(cells[2].xpath('.//div[contains(@style, "bold")]//text()').get()),
                "status": clean(cells[3].xpath("string(.)").get()),
                "bids_start": clean(cells[4].xpath("string(.)").get()),
                "lots_url": f"{LOTS_PATH}?perspective=inline&id={purchase.group(1)}",
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Наименьший номер в пейджере больше текущего; ``None`` — страница последняя."""
    pages = [
        int(match.group(1))
        for href in page.xpath('//a[contains(@href, "list.html?page=")]/@href').getall()
        if (match := _PAGE_RE.search(href))
    ]
    later = [p for p in pages if p > num_page]
    return min(later) if later else None
