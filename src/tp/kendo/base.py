"""Базовый парсер движка Kendo-ETP.

Листинг ``/lots`` — карточки ``block-lot``: на одних площадках карточка на
торги (``<a>``), на других — на лот (``<div>``). В обоих вариантах есть ссылка
«Номер торгов» ``/{тип}/{id}`` — адрес торгов. Лоты и цены — только на
странице торгов: ``div#lots``; организатор и сроки — пары ``div.table_row`` в
``div#main-info``. Повторный заход в одни торги отсекает дедупликация
запросов фреймворка.

Площадка наследует ``Kendo`` и задаёт ``name`` и ``DOMAIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits, local_href
from core.lot import Lot


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
                "trade_url": local_href(trade_url),
                "bids_end": clean(card.xpath('.//nobr[i[@title="Окончание приема заявок"]]/text()').get()),
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> tuple[int, str] | None:
    """Номер и ссылка ближайшей следующей страницы пейджера; ``None`` — страница последняя.

    Берётся ссылка самого пейджера, а не собранный адрес: в ней уже все
    параметры листинга, которые площадка сочла нужными. Схема и хост
    отрезаются (``local_href``): пейджер у части площадок ссылается на http.
    """
    later = []
    for href in page.xpath('//ul[contains(@class, "pagination")]//a[contains(@href, "page=")]/@href').getall():
        n = digits(href.split("page=", 1)[1])
        if n and int(n) > num_page:
            later.append((int(n), local_href(href)))
    return min(later) if later else None


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


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Лоты из ``div#lots`` -> поля ``Lot`` без ``source`` и адресов.

    ``lot_href`` — ссылка на страницу лота как в разметке; сроки и организатор —
    со страницы торгов, срок из карточки листинга — запасной.
    """
    main = parse_main_info(page)
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "debtor": debtor_of(trade.get("trade_title")),
        "organizer": main.get("Наименование"),
        "bids_end": main.get("Окончание приема заявок") or trade.get("bids_end"),
        "auction_date": main.get("Подведение результатов торгов"),
    }
    lots = []
    for block in page.xpath('//div[@id="lots"]//*[contains(@class, "block-lot")]'):
        link = block.xpath('.//a[contains(@href, "/lots/")][1]')
        lot_num = clean(block.xpath('.//span[contains(@class, "black-text")]/text()').get())
        if not lot_num:
            continue
        lots.append(
            {
                **shared,
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "lot_num": lot_num,
                "lot_href": link.xpath("./@href").get(),
                "description": clean(link.xpath("string(.)").get()),
                "price": clean(block.xpath('string(.//span[contains(@class, "fs36")])').get()),
                "status": clean(
                    block.xpath('.//span[contains(@class, "lot-status")]/following-sibling::text()').get()
                ),
            }
        )
    return lots


@dataclass(frozen=True)
class KendoParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class Kendo(Crawler):

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "lots"

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50,
    )
    params = KendoParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга — из домена площадки.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Страница листинга: зайти в каждые торги, затем следующая страница."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        trades = parse_listing(page)
        await self.log(f"страница {num_page}: торгов {len(trades)}")

        for trade in trades:
            yield response.follow(trade["trade_url"], callback = self.parse_trade, metadata = {"trade": trade})

        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            number, href = next_page
            yield response.follow(href, metadata = {"num_page": number})

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по ``Lot`` на лот."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        trade_url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            href = lot.pop("lot_href")
            yield Lot(
                source = self.name,
                lot_url = response.urljoin(href) if href else trade_url,
                trade_url = trade_url,
                **lot,
            ).model_dump()
