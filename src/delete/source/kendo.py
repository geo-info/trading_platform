"""TenderKendo — площадки банкротных торгов на движке Kendo-ETP.

Лоты собираются по статусам прогона (параметр ``statuses``, названия через
запятую): поиск GET-формой листинга со статусом -> перелистывание -> поиск со
следующим статусом. Коды статусов у площадок разные («Объявлен» где 3, где 2),
поэтому статус — название, а код берётся из формы площадки (``tp.search``).

Листинг ``/lots`` — карточки ``block-lot``: на одних площадках карточка на
торги (``<a>``), на других — на лот (``<div>``). В обоих вариантах есть ссылка
«Номер торгов» ``/{тип}/{id}`` — адрес торгов. Лоты и цены — только на
странице торгов: ``div#lots``, сведения о торгах — пары ``div.table_row`` в
``div#main-info``, документы — ``div#documents``. Повторный заход в одни
торги отсекает дедупликация запросов фреймворка.

Разбор перенесён из справочника, регулярные выражения заменены на XPath и
строковые операции. Площадки — ``tp.kendo_platforms``, запуск — ``tp.run_kendo``.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from itertools import takewhile
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.help import clean
from core.conf import settings as config
from tp.delete.search import (
    SearchParams,
    check_status,
    listing_request,
    norm,
    search_fields,
    split_statuses,
    status_choices,
)

#: Поле статуса в форме листинга.
STATUS_FIELD = "status_id"
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


def digits(text: str | None) -> str:
    """Ведущие цифры строки: «10840–ОАОФ» -> «10840»."""
    return "".join(takewhile(str.isdigit, text or ""))


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
        detail_url = card.xpath("./@href").get() or number_href
        trade_id = digits(number)
        if not trade_id or not detail_url or trade_id in seen:
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
                "bidding_date": clean(
                    card.xpath('.//nobr[i[@title="Окончание приема заявок"]]/text()').get()
                ),
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


def parse_documents(page: Selector) -> list[dict[str, Any]]:
    """Документы торгов: имя и ссылка из ``#documents``."""
    documents = []
    for row in page.xpath('//div[@id="documents"]//div[contains(@class, "file-row")]'):
        link = row.xpath('.//a[starts-with(@href, "http")][1]')
        if url := link.xpath("./@href").get():
            documents.append({"name": clean(link.xpath("string(.)").get()), "url": url})
    return documents


def debtor_of(title: str | None) -> str | None:
    """Должник — хвост заголовка карточки «…, должник X» (или «должника X»)."""
    at = (title or "").lower().rfind("должник")
    parts = (title or "")[at:].split(maxsplit=1) if at >= 0 else []
    return parts[1].strip() if len(parts) == 2 else None


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Лоты из ``div#lots``; сроки и организатор — со страницы торгов, не из карточки."""
    main = parse_main_info(page)
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "debtor": debtor_of(trade.get("trade_title")),
        "organizer": main.get("Наименование"),
        "bids_end": main.get("Окончание приема заявок") or trade.get("bidding_date"),
        "auction_date": main.get("Подведение результатов торгов"),
        "detail": main,
        "attachments": parse_documents(page),
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
                "lot_url": link.xpath("./@href").get(),
                "description": clean(link.xpath("string(.)").get()),
                "price": clean(block.xpath('string(.//span[contains(@class, "fs36")])').get()),
                "status": clean(
                    block.xpath('.//span[contains(@class, "lot-status")]/following-sibling::text()').get()
                ),
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class TenderKendo(Crawler):
    """Наследнику-площадке достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "lots"

    settings = Settings(
        concurrency=1, delay=config.parsing.delay, timeout=config.parsing.http_timeout, max_errors=50
    )
    params = SearchParams(statuses=ACTIVE)

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга выводится из домена; у базы движка домена нет.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Стартовая страница: найти в форме статусы прогона и начать с первого."""
        check_status(response)
        page = response.selector()
        choices = status_choices(page, STATUS_FIELD)
        self.searches = []
        for name in split_statuses(self.params.statuses):
            if (choice := choices.get(norm(name))) is None:
                await self.log(f"статуса «{name}» в форме площадки нет — пропускаю")
                continue
            self.searches.append((choice, *search_fields(page, response.request.url, choice)))
        if self.searches:
            yield self.search(0)

    def search(self, index: int) -> Any:
        choice, action, fields = self.searches[index]
        return listing_request(self, action, fields, "page", 1, {"search": index})

    async def parse_listing(self, response: Response) -> Any:
        """Страница выдачи: зайти в каждые торги, затем следующая страница или статус."""
        check_status(response)
        page = response.selector()
        index, num_page = response.metadata["search"], response.metadata["page"]
        choice, action, fields = self.searches[index]
        trades = parse_listing(page)
        await self.log(f"«{choice.label}»: страница {num_page}, торгов {len(trades)}")
        for trade in trades:
            yield response.follow(
                trade["detail_url"],
                callback=self.parse_trade,
                metadata={"trade": trade, "status": choice.label},
            )
        next_page = find_next_page(page, num_page)
        if next_page is not None and num_page < self.params.max_pages:
            yield listing_request(self, action, fields, "page", next_page, {"search": index})
        elif index + 1 < len(self.searches):
            yield self.search(index + 1)

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по айтему на лот."""
        check_status(response)
        fetched_at = datetime.now(UTC).isoformat()
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            yield {
                "source": self.name,
                "url": response.urljoin(lot["lot_url"]) if lot["lot_url"] else response.request.url,
                "fetched_at": fetched_at,
                "searched_status": response.metadata["status"],
                **lot,
            }


def narrow(**overrides: Any) -> Settings:
    """Настройки площадки: общие плюс её особенность."""
    return replace(TenderKendo.settings, **overrides)
