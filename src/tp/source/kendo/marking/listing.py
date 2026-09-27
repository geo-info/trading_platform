"""Разметка листинга Kendo-ETP: карточки ``block-lot`` и пейджер.

На одних площадках карточка на торги (``<a>``), на других — на лот (``<div>``);
в обоих вариантах есть ссылка «Номер торгов» ``/{тип}/{id}`` — адрес торгов.
Разбор перенесён из coll-temp (``collector/sources/kendo``).
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean

_PAGE_RE = re.compile(r"page=(\d+)")


_DIGITS_RE = re.compile(r"\d+")


#: «10775–ОАОФ» / «37-ОАОФ»: цифры, затем тире или дефис. Отличает номер
#: торгов от названия среди жирных строк карточки.
_NUMBER_RE = re.compile(r"^\d+\s*[–-]")


def _date_by_title(card: Selector, title: str) -> str | None:
    return clean(card.xpath(f'.//nobr[i[@title="{title}"]]/text()').get())


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Страница листинга -> торги, без повторов внутри страницы.

    Номер торгов ищется среди жирных строк карточки по виду «цифры–тип», а не
    по тегу и цвету: на площадках с карточкой на торги он простой текст, на
    площадках с карточкой на лот — ссылка. Поля карточки — приблизительные:
    авторитетные сведения о торгах берутся со страницы торгов.
    """
    trades: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in page.xpath('//*[contains(@class, "block-lot")]'):
        number = number_href = title = None
        for bold in card.xpath('.//*[contains(@class, "bold")]'):
            text = clean(bold.xpath("string(.)").get())
            if not text:
                continue
            if _NUMBER_RE.match(text):
                number = text
                number_href = bold.xpath(".//a/@href").get()
            elif title is None:
                title = text
        # Адрес торгов: сама карточка-ссылка или ссылка номера в карточке лота.
        detail_url = card.xpath("./@href").get() or number_href
        if not number or not detail_url:
            continue
        digits = _DIGITS_RE.search(number)
        trade_id = digits.group(0) if digits else None
        if not trade_id or trade_id in seen:
            continue
        seen.add(trade_id)
        parts = number.split("–")
        trades.append(
            {
                "trade_id": trade_id,
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "trade_title": title,
                "detail_url": detail_url,
                "status": clean(
                    card.xpath('.//span[contains(@class, "competition-status-text")]/text()').get()
                ),
                "bidding_date": _date_by_title(card, "Окончание приема заявок"),
                "event_date": _date_by_title(card, "Подведение итогов"),
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Наименьший номер в пейджере больше текущего; ``None`` — страница последняя."""
    pages = [
        int(match.group(1))
        for href in page.xpath(
            '//ul[contains(@class, "pagination")]//a[contains(@href, "page=")]/@href'
        ).getall()
        if (match := _PAGE_RE.search(href))
    ]
    later = [p for p in pages if p > num_page]
    return min(later) if later else None
