"""Базовый парсер движка Kendo-ETP.

Листинг ``/lots`` — карточки ``block-lot``, поиск по статусу — GET-форма с
полем ``status_id`` (см. ``tp.common.search.StatusSearch``). На одних площадках
карточка на торги (``<a>``), на других — на лот (``<div>``); в обоих
вариантах есть ссылка «Номер торгов» ``/{тип}/{id}`` — адрес торгов. Лоты и
цены — только на странице торгов: ``div#lots``, сведения о торгах — пары
``div.table_row`` в ``div#main-info``, документы — ``div#documents``. Повторный
заход в одни торги отсекает дедупликация запросов фреймворка.

Площадка наследует ``Kendo`` и задаёт ``name`` и ``DOMAIN``.
"""

from __future__ import annotations

from typing import Any

from collector import Request, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits
from core.lot import Lot
from tp.common.search import SearchParams, StatusSearch
from tp.common.site import check_status

#: Все названия статусов, что встречаются на площадках движка.
KNOWN_STATUSES = [
    "На утверждении",
    "Объявлен",
    "Идет прием заявок",
    "Прием заявок окончен",
    "Прием заявок завершен",
    "Прием заявок приостановлен",
    "В стадии проведения",
    "Ожидание начала следующего шага",
    "Торги завершены",
    "Торги приостановлены",
    "Торги отменены",
    "Торги по лоту отменены",
]
#: Актуальные по умолчанию: торги объявлены или идёт приём заявок.
ACTIVE = "Объявлен,Идет прием заявок"


# ── листинг ──────────────────────────────────────────────────────────────────


def is_trade_number(text: str) -> bool:
    """«10775–ОАОФ» / «37-ОАОФ»: цифры, затем тире или дефис.

    Так номер торгов отличается от названия среди жирных строк карточки.
    """
    head = digits(text)
    return bool(head) and text[len(head) :].lstrip()[:1] in ("–", "-")


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Страница листинга -> торги, без повторов внутри страницы."""
    trades: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in page.xpath('//*[contains(@class, "block-lot")]'):
        number = number_href = title = None
        for bold in card.xpath('.//*[contains(@class, "bold")]'):
            text = clean(bold.xpath("string(.)").get())
            if not text:
                continue
            if is_trade_number(text):
                number, number_href = text, bold.xpath(".//a/@href").get()
            elif title is None:
                title = text
        # Адрес торгов: сама карточка-ссылка или ссылка номера в карточке лота.
        trade_url = card.xpath("./@href").get() or number_href
        trade_id = digits(number)
        if not trade_id or not trade_url or trade_id in seen:
            continue
        seen.add(trade_id)
        parts = number.split("–")
        trades.append(
            {
                "trade_id": trade_id,
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "trade_title": title,
                "trade_url": trade_url,
                "status": clean(
                    card.xpath('.//span[contains(@class, "competition-status-text")]/text()').get()
                ),
                "bids_end": clean(card.xpath('.//nobr[i[@title="Окончание приема заявок"]]/text()').get()),
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Наименьший номер в пейджере больше текущего; ``None`` — страница последняя."""
    numbers = page.xpath('//ul[contains(@class, "pagination")]//a[contains(@href, "page=")]/@href').getall()
    later = [int(n) for href in numbers if (n := digits(href.split("page=", 1)[1])) and int(n) > num_page]
    return min(later) if later else None


# ── страница торгов ──────────────────────────────────────────────────────────


def parse_main_info(page: Selector) -> dict[str, str]:
    """Пары «подпись: значение» из ``#main-info``; повторная подпись — выигрывает последняя."""
    info: dict[str, str] = {}
    for row in page.xpath('//div[@id="main-info"]//div[contains(@class, "table_row")]'):
        label = clean(row.xpath('string(./div[contains(@class, "grey-text")][1])').get())
        value = clean(row.xpath('string(./div[contains(@class, "l9")][1])').get())
        if label and value:
            info[label.rstrip(":").strip()] = value
    return info


def debtor_of(title: str | None) -> str | None:
    """Должник — хвост заголовка карточки «…, должник X» (или «должника X»)."""
    at = (title or "").lower().rfind("должник")
    parts = (title or "")[at:].split(maxsplit=1) if at >= 0 else []
    return parts[1].strip() if len(parts) == 2 else None


def lot_blocks(page: Selector) -> list[tuple[str, Selector]]:
    """Карточки лотов ``div#lots``: номер лота -> карточка."""
    blocks = []
    for block in page.xpath('//div[@id="lots"]//*[contains(@class, "block-lot")]'):
        if lot_num := clean(block.xpath('.//span[contains(@class, "black-text")]/text()').get()):
            blocks.append((lot_num, block))
    return blocks


def lot_link(block: Selector) -> Selector:
    return block.xpath('.//a[contains(@href, "/lots/")][1]')


def lot_price(block: Selector) -> str | None:
    return clean(block.xpath('string(.//span[contains(@class, "fs36")])').get())


def lot_status(block: Selector) -> str | None:
    return clean(block.xpath('.//span[contains(@class, "lot-status")]/following-sibling::text()').get())


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Лоты страницы торгов; сроки и организатор — со страницы торгов, не из карточки."""
    main = parse_main_info(page)
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "auction_name": trade.get("trade_title"),
        "debtor": debtor_of(trade.get("trade_title")),
        "organizer": main.get("Наименование"),
        "bids_end": main.get("Окончание приема заявок") or trade.get("bids_end"),
        "auction_date": main.get("Подведение результатов торгов"),
    }
    lots = []
    for lot_num, block in lot_blocks(page):
        link = lot_link(block)
        lots.append(
            {
                **shared,
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "lot_num": lot_num,
                "lot_url": link.xpath("./@href").get(),
                "description": clean(link.xpath("string(.)").get()),
                "price": lot_price(block),
                "status": lot_status(block) or trade.get("status"),
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class Kendo(StatusSearch):

    LISTING_PATH = "lots"
    STATUS_FIELD = "status_id"

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50,
    )
    params = SearchParams(statuses = ACTIVE)

    parse_listing = staticmethod(parse_listing)
    find_next_page = staticmethod(find_next_page)

    def trade_request(self, response: Response, trade: dict[str, Any]) -> Request:
        return response.follow(trade["trade_url"], callback = self.parse_trade, metadata = {"trade": trade})

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по айтему на лот."""
        check_status(response)
        trade_url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            lot_url = response.urljoin(lot["lot_url"]) if lot["lot_url"] else trade_url
            yield Lot(source = self.name, **{**lot, "lot_url": lot_url}, trade_url = trade_url).model_dump()
