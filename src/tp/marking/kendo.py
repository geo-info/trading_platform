"""Разметка площадок на движке Kendo-ETP: листинг и страница торгов.

Листинг ``/lots?page=N`` — карточки ``block-lot``: на одних площадках карточка
на торги (``<a>``), на других — на лот (``<div>``). В обоих вариантах в карточке
есть ссылка «Номер торгов» ``/{тип}/{id}`` — адрес торгов; по ней листинг
сводится к торгам. Страница торгов серверная, со всеми вкладками сразу: лоты —
``div#lots``, сведения о торгах — пары ``div.table_row`` в ``div#main-info``,
документы — ``div#documents``.

Разбор перенесён из coll-temp (``collector/sources/kendo``).

Как обходить площадку — в ``tp.kendo``.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean, parse_price

_PAGE_RE = re.compile(r"page=(\d+)")
_DIGITS_RE = re.compile(r"\d+")
#: «10775–ОАОФ» / «37-ОАОФ»: цифры, затем тире или дефис. Отличает номер
#: торгов от названия среди жирных строк карточки.
_NUMBER_RE = re.compile(r"^\d+\s*[–-]")
#: Должник — хвост заголовка карточки «…, должник X».
_DEBTOR_RE = re.compile(r"должник[аи]?\s+(.+)$", re.IGNORECASE)


# ── листинг ──────────────────────────────────────────────────────────────────


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


# ── страница торгов ──────────────────────────────────────────────────────────


def parse_main_info(page: Selector) -> dict[str, str]:
    """Пары «подпись: значение» из ``#main-info``.

    Подпись, повторённая в разных разделах, схлопывается — выигрывает
    последняя. Для справочного ``extra`` это приемлемо.
    """
    info: dict[str, str] = {}
    for row in page.xpath('//div[@id="main-info"]//div[contains(@class, "table_row")]'):
        label = clean(row.xpath('string(./div[contains(@class, "grey-text")][1])').get())
        value = clean(row.xpath('string(./div[contains(@class, "l9")][1])').get())
        if label and value:
            info[label.rstrip(":").strip()] = value
    return info


def parse_documents(page: Selector) -> list[dict[str, Any]]:
    """Документы торгов: имя и ссылка из ``#documents``."""
    documents: list[dict[str, Any]] = []
    for row in page.xpath('//div[@id="documents"]//div[contains(@class, "file-row")]'):
        link = row.xpath('.//a[starts-with(@href, "http")][1]')
        if url := link.xpath("./@href").get():
            documents.append({"name": clean(link.xpath("string(.)").get()), "url": url})
    return documents


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Лоты торгов из ``div#lots``; сведения о торгах — со страницы, а не из листинга.

    На площадках с карточкой на лот поля карточки относятся к лоту, а не к
    торгам, поэтому сроки, организатор и должник берутся со страницы торгов.
    """
    main = parse_main_info(page)
    debtor = _DEBTOR_RE.search(trade.get("trade_title") or "")
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "debtor": debtor.group(1).strip() if debtor else None,
        "organizer": main.get("Наименование"),
        "bidding_date": main.get("Окончание приема заявок") or trade.get("bidding_date"),
        "event_date": main.get("Подведение результатов торгов") or trade.get("event_date"),
        "detail": main,
        "attachments": parse_documents(page),
    }
    lots: list[dict[str, Any]] = []
    for block in page.xpath('//div[@id="lots"]//*[contains(@class, "block-lot")]'):
        link = block.xpath('.//a[contains(@href, "/lots/")][1]')
        lot_num = clean(block.xpath('.//span[contains(@class, "black-text")]/text()').get())
        price_raw = clean(block.xpath('string(.//span[contains(@class, "fs36")])').get())
        lots.append(
            {
                **shared,
                "lot_id": f"{trade['trade_id']}_{lot_num}" if lot_num else None,
                "lot_num": lot_num,
                "lot_url": link.xpath("./@href").get(),
                "description": clean(link.xpath("string(.)").get()),
                "price": parse_price(price_raw),
                "price_raw": price_raw,
                "status": clean(
                    block.xpath('.//span[contains(@class, "lot-status")]/following-sibling::text()').get()
                ),
            }
        )
    return lots
