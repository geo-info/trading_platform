"""Разметка страницы торгов Kendo-ETP: лоты, сведения о торгах, документы.

Страница серверная, со всеми вкладками сразу: лоты — ``div#lots``, сведения о
торгах — пары ``div.table_row`` в ``div#main-info``, документы — ``div#documents``.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean, parse_price

#: Должник — хвост заголовка карточки «…, должник X».
_DEBTOR_RE = re.compile(r"должник[аи]?\s+(.+)$", re.IGNORECASE)


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
