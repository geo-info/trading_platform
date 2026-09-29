"""Базовый парсер движка btorg (edoc-ETP).

Листинг ``/etp/trade/list.html`` — ``table.data``, строка на торги; поиск по
статусу — GET-форма с полем ``processStatus`` (см. ``tp.common.search.StatusSearch``).
Отдельного фильтра «торги объявлены» у движка нет: из актуальных фильтруется
только «идёт приём заявок».

Цен в листинге нет, поэтому в каждые торги заходим за AJAX-фрагментом лотов
``inner-view-lots.html`` (с признаком XHR). Во фрагменте — по ``table.data``
на лот (``id="lotNumberN"``) с парами «подпись — значение» и, у публичного
предложения, вложенной таблицей интервалов снижения цены. Страницы — в
windows-1251, перекодирует их фреймворк по заголовку ответа.

Площадка наследует ``Btorg`` и задаёт ``name`` и ``DOMAIN``.
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

KNOWN_STATUSES = [
    "идёт приём заявок",
    "приём заявок завершен",
    "в стадии проведения",
    "подводятся итоги",
    "торги завершены",
    "торги отменены",
]
#: Актуальный по умолчанию. «Торги объявлены» движок отдельно не фильтрует.
ACTIVE = "идёт приём заявок"

#: AJAX-фрагмент с лотами торгов — с ценами, которых нет в листинге.
LOTS_PATH = "/etp/trade/inner-view-lots.html"
#: Фрагмент лотов отдаётся только на AJAX-запрос.
XHR = {"X-Requested-With": "XMLHttpRequest"}


# ── листинг ──────────────────────────────────────────────────────────────────


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Строки ``table.data`` -> торги.

    Внутренний id торгов, по которому запрашиваются лоты, и адрес страницы
    торгов — в ``onclick`` строки (``window.location='…general.html?id=NNN'``).
    Колонка «Организатор» идёт перед «Должником».
    """
    trades = []
    for row in page.xpath('//table[@class="data"]//tr[@onclick]'):
        onclick = row.attrib["onclick"]
        purchase = digits(onclick.partition("id=")[2])
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
                "bids_start": clean(cells[4].xpath("string(.)").get()),
                "trade_page": onclick.partition("window.location='")[2].partition("'")[0] or None,
                "lots_url": f"{LOTS_PATH}?perspective=inline&id={purchase}",
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Наименьший номер в пейджере больше текущего; ``None`` — страница последняя."""
    numbers = page.xpath('//a[contains(@href, "list.html?page=")]/@href').getall()
    later = [int(n) for href in numbers if (n := digits(href.split("page=", 1)[1])) and int(n) > num_page]
    return min(later) if later else None


# ── фрагмент лотов ───────────────────────────────────────────────────────────


def lot_tables(page: Selector) -> list[tuple[str, Selector]]:
    """Таблицы ``lotNumberN`` фрагмента: номер лота -> таблица."""
    return [
        (lot_num, table)
        for table in page.xpath('//table[contains(@id, "lotNumber")]')
        if (lot_num := table.xpath('substring-after(@id, "lotNumber")').get())
    ]


def lot_pairs(lot: Selector) -> dict[str, str]:
    """Пары «подпись — значение» таблицы лота.

    Только свои строки таблицы: строки вложенной таблицы интервалов дали бы
    подписи-даты.
    """
    own_rows = lot.xpath(".//tr[td[2]][ancestor::table[1][contains(@id, 'lotNumber')]]")
    return {
        label.rstrip(":").strip(): value
        for row in own_rows
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
    """Лоты фрагмента; сведения о торгах — из листинга."""
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
                # Срок приёма публичного предложения — конец последнего интервала;
                # дата из листинга — это его начало, а не срок.
                "bids_end": schedule[-1].get("Дата окончания приема заявок") if schedule else None,
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class Btorg(StatusSearch):

    LISTING_PATH = "etp/trade/list.html"
    STATUS_FIELD = "processStatus"

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
        return response.follow(
            trade["lots_url"], callback = self.parse_trade, headers = XHR, metadata = {"trade": trade}
        )

    async def parse_trade(self, response: Response) -> Any:
        """Фрагмент лотов торгов: по айтему на лот.

        Своей страницы у лота нет: для человека — страница торгов, детали —
        из того же фрагмента (``trade_url``).
        """
        check_status(response)
        trade = response.metadata["trade"]
        trade_url = response.request.url
        lot_url = response.urljoin(trade["trade_page"]) if trade.get("trade_page") else trade_url
        for lot in parse_lots(response.selector(), trade):
            yield Lot(source = self.name, lot_url = lot_url, trade_url = trade_url, **lot).model_dump()
