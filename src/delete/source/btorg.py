"""TenderBtorg — площадки банкротных торгов на движке btorg (edoc-ETP).

Лоты собираются по статусам прогона (параметр ``statuses``, названия через
запятую): поиск GET-формой листинга со статусом (поле ``processStatus``) ->
перелистывание -> поиск со следующим статусом. Отдельного фильтра «торги
объявлены» у движка нет: из актуальных фильтруется только «идёт приём заявок».

Листинг ``/etp/trade/list.html`` — ``table.data``, строка на торги; цен в нём
нет, поэтому в каждые торги заходим за AJAX-фрагментом лотов
``inner-view-lots.html`` (с признаком XHR). Во фрагменте — по ``table.data``
на лот (``id="lotNumberN"``) с парами «подпись — значение» и, у публичного
предложения, вложенной таблицей интервалов снижения цены. Страницы — в
windows-1251, перекодирует их фреймворк по заголовку ответа.

Разбор перенесён из справочника, регулярные выражения заменены на XPath и
строковые операции. Площадки — ``tp.btorg_platforms``, запуск — ``tp.run_btorg``.
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
STATUS_FIELD = "processStatus"
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


def digits(text: str | None) -> str:
    """Ведущие цифры строки: «13147-ОТПП» -> «13147»."""
    return "".join(takewhile(str.isdigit, text or ""))


# ── листинг ──────────────────────────────────────────────────────────────────


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Строки ``table.data`` -> торги.

    Внутренний id торгов, по которому запрашиваются лоты, — в ``onclick``
    строки (``…general.html?id=NNN…``). В coll-temp организатор и должник были
    перепутаны: колонка «Организатор» идёт перед «Должником».
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
                "bids_start": clean(cells[4].xpath("string(.)").get()),
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


def property_details(detail: dict[str, str]) -> str | None:
    """«Сведения об имуществе должника…» — описание, где «Предмет торгов» не заполнен.

    Ищется по вхождению: первая «С» в подписи на части площадок латинская.
    """
    return next((value for label, value in detail.items() if "ведения об имуществе" in label), None)


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


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Таблицы ``lotNumberN`` фрагмента -> лоты; сведения о торгах — из листинга."""
    lots = []
    for lot in page.xpath('//table[contains(@id, "lotNumber")]'):
        lot_num = lot.xpath('substring-after(@id, "lotNumber")').get()
        if not lot_num:
            continue
        # Только свои строки таблицы лота — строки вложенной таблицы интервалов
        # дали бы в detail подписи-даты.
        own_rows = lot.xpath(".//tr[td[2]][ancestor::table[1][contains(@id, 'lotNumber')]]")
        detail = {
            label.rstrip(":").strip(): value
            for row in own_rows
            if (label := clean(row.xpath("string(./td[1])").get()))
            and (value := clean(row.xpath("string(./td[2])").get()))
        }
        schedule = parse_schedule(lot)
        lots.append(
            {
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "trade_id": trade["trade_id"],
                "trade_number": trade.get("trade_number"),
                "trade_type": trade.get("trade_type"),
                "lot_num": lot_num,
                "debtor": trade.get("debtor"),
                "organizer": trade.get("organizer"),
                "description": detail.get("Предмет торгов") or property_details(detail),
                "price": detail.get("Начальная цена продажи имущества"),
                "status": detail.get("Статус торгов") or trade.get("status"),
                # Срок приёма публичного предложения — конец последнего интервала;
                # дата из листинга — это его начало, а не срок.
                "bids_end": schedule[-1].get("Дата окончания приема заявок") if schedule else None,
                "detail": {**detail, "Начало приема заявок": trade.get("bids_start")},
                "price_schedule": schedule,
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class TenderBtorg(Crawler):
    """Наследнику-площадке достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "etp/trade/list.html"

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
        """Страница выдачи: зайти за лотами каждых торгов, затем следующая страница или статус."""
        check_status(response)
        page = response.selector()
        index, num_page = response.metadata["search"], response.metadata["page"]
        choice, action, fields = self.searches[index]
        trades = parse_listing(page)
        await self.log(f"«{choice.label}»: страница {num_page}, торгов {len(trades)}")
        for trade in trades:
            yield response.follow(
                trade["lots_url"],
                callback=self.parse_trade,
                headers=XHR,
                metadata={"trade": trade, "status": choice.label},
            )
        next_page = find_next_page(page, num_page)
        if next_page is not None and num_page < self.params.max_pages:
            yield listing_request(self, action, fields, "page", next_page, {"search": index})
        elif index + 1 < len(self.searches):
            yield self.search(index + 1)

    async def parse_trade(self, response: Response) -> Any:
        """Фрагмент лотов торгов: по айтему на лот. Своей страницы у лота нет —
        его адрес это адрес фрагмента."""
        check_status(response)
        fetched_at = datetime.now(UTC).isoformat()
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            yield {
                "source": self.name,
                "url": response.request.url,
                "fetched_at": fetched_at,
                "searched_status": response.metadata["status"],
                **lot,
            }


def narrow(**overrides: Any) -> Settings:
    """Настройки площадки: общие плюс её особенность."""
    return replace(TenderBtorg.settings, **overrides)
