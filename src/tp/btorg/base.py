"""Базовый парсер движка btorg (edoc-ETP).

Листинг ``/etp/trade/list.html`` — ``table.data``, строка на торги; цен в нём
нет, поэтому в каждые торги заходим за AJAX-фрагментом лотов
``inner-view-lots.html`` (с признаком XHR). Во фрагменте — по ``table.data``
на лот (``id="lotNumberN"``) с парами «подпись — значение» и, у публичного
предложения, вложенной таблицей интервалов снижения цены. Своей страницы у
лота нет: его адрес для человека — страница торгов ``general.html`` (фрагмент
без признака XHR не отдаётся), детали берутся из фрагмента. Страницы — в windows-1251,
перекодирует их фреймворк по заголовку ответа.

Площадка наследует ``Btorg`` и задаёт ``name`` и ``DOMAIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits, local_href
from core.lot import Lot
from core.registry import register

#: AJAX-фрагмент с лотами торгов — с ценами, которых нет в листинге.
LOTS_PATH = "/etp/trade/inner-view-lots.html"
#: Страница торгов для человека — та, на которую ведёт строка листинга.
#: Путь без ``/etp``: с ним площадка отвечает 500.
TRADE_PAGE_PATH = "/trade/view/purchase/general.html"
#: Фрагмент лотов отдаётся только на AJAX-запрос.
XHR = {"X-Requested-With": "XMLHttpRequest"}


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Строки ``table.data`` -> торги.

    Внутренний id торгов, по которому запрашиваются лоты, — в ``onclick``
    строки (``…general.html?id=NNN…``). Колонка «Организатор» идёт перед
    «Должником».
    """
    trades = []
    for row in page.xpath('//table[@class="data"]//tr[@onclick]'):
        purchase = digits(row.xpath('substring-after(@onclick, "id=")').get())
        cells = row.xpath("./td")
        number = clean(cells[0].xpath("string(.)").get()) if cells else None
        if not purchase or len(cells) < 5 or not digits(number):
            continue
        parts = number.split("-")
        trades.append(
            {
                "trade_id": digits(number),
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "organizer": clean(cells[1].xpath("string(.)").get()),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(cells[2].xpath('.//div[contains(@style, "bold")]//text()').get()),
                "status": clean(cells[3].xpath("string(.)").get()),
                "trade_url": f"{LOTS_PATH}?perspective=inline&id={purchase}",
                "page_url": f"{TRADE_PAGE_PATH}?id={purchase}",
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> tuple[int, str] | None:
    """Номер и ссылка ближайшей следующей страницы пейджера; ``None`` — страница последняя.

    Схема и хост отрезаются (``local_href``): пейджер у части площадок ссылается на http.
    """
    later = []
    for href in page.xpath('//a[contains(@href, "list.html?page=")]/@href').getall():
        n = digits(href.split("page=", 1)[1])
        if n and int(n) > num_page:
            later.append((int(n), local_href(href)))
    return min(later) if later else None


def lot_tables(page: Selector) -> list[tuple[str, Selector]]:
    """Таблицы лотов фрагмента: номер лота и таблица ``lotNumberN``."""
    tables = []
    for table in page.xpath('//table[contains(@id, "lotNumber")]'):
        if lot_num := table.xpath('substring-after(@id, "lotNumber")').get():
            tables.append((lot_num, table))
    return tables


def lot_pairs(lot: Selector) -> dict[str, str]:
    """Пары «подпись: значение» таблицы лота.

    Только свои строки таблицы лота — строки вложенной таблицы интервалов
    дали бы подписи-даты.
    """
    rows = lot.xpath(".//tr[td[2]][ancestor::table[1][contains(@id, 'lotNumber')]]")
    return {
        label.rstrip(":").strip(): value
        for row in rows
        if (label := clean(row.xpath("string(./td[1])").get()))
        and (value := clean(row.xpath("string(./td[2])").get()))
    }


def parse_schedule(lot: Selector) -> list[dict[str, str]]:
    """Интервалы снижения цены публичного предложения: строка -> {заголовок: ячейка}."""
    table = lot.xpath('.//table[contains(@class, "inner")]')
    headers = [clean(td.xpath("string(.)").get()) or "" for td in table.xpath(".//tr[1]/*")]
    schedule = []
    for row in table.xpath(".//tr[position() > 1]"):
        cells = [clean(td.xpath("string(.)").get()) or "" for td in row.xpath("./td")]
        if headers and len(cells) == len(headers):
            schedule.append(dict(zip(headers, cells, strict=True)))
    return schedule


def property_details(pairs: dict[str, str]) -> str | None:
    """«Сведения об имуществе должника…» — описание, где «Предмет торгов» не заполнен.

    Ищется по вхождению: первая «С» в подписи на части площадок латинская.
    """
    return next((value for label, value in pairs.items() if "ведения об имуществе" in label), None)


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Таблицы ``lotNumberN`` фрагмента -> поля ``Lot`` без ``source`` и адресов."""
    lots = []
    for lot_num, table in lot_tables(page):
        pairs = lot_pairs(table)
        schedule = parse_schedule(table)
        lots.append(
            {
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "trade_id": trade["trade_id"],
                "trade_number": trade.get("trade_number"),
                "trade_type": trade.get("trade_type"),
                "lot_num": lot_num,
                "debtor": trade.get("debtor"),
                "organizer": trade.get("organizer"),
                "description": pairs.get("Предмет торгов") or property_details(pairs),
                "price": pairs.get("Начальная цена продажи имущества"),
                "status": pairs.get("Статус торгов") or trade.get("status"),
                # Срок приёма публичного предложения — конец последнего интервала.
                "bids_end": schedule[-1].get("Дата окончания приема заявок") if schedule else None,
            }
        )
    return lots


@dataclass(frozen=True)
class BtorgParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class Btorg(Crawler):
    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "etp/trade/list.html"

    settings = Settings(
        concurrency=1,
        delay=conf.parsing.delay,
        timeout=conf.parsing.http_timeout,
        max_errors=50,
    )
    params = BtorgParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга — из домена площадки.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]
            register(cls)

    async def parse(self, response: Response) -> Any:
        """Страница листинга: зайти за лотами каждых торгов, затем следующая страница."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        trades = parse_listing(page)
        await self.log(f"страница {num_page}: торгов {len(trades)}")

        for trade in trades:
            yield response.follow(
                trade["trade_url"], callback=self.parse_trade, headers=XHR, metadata={"trade": trade}
            )

        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            number, href = next_page
            yield response.follow(href, metadata={"num_page": number})

    async def parse_trade(self, response: Response) -> Any:
        """Фрагмент лотов торгов: по ``Lot`` на лот; адрес лота — страница торгов."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        trade = response.metadata["trade"]
        lot_url, trade_url = response.urljoin(trade["page_url"]), response.request.url
        for lot in parse_lots(response.selector(), trade):
            yield Lot(source=self.name, lot_url=lot_url, trade_url=trade_url, **lot).model_dump()
