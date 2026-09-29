"""TenderRuson — площадки банкротных торгов на движке rus-on.

Лоты собираются по статусам прогона (параметр ``statuses``, названия через
запятую): поиск GET-формой листинга со статусом -> перелистывание -> поиск со
следующим статусом. Поле статуса — ``trade_state``: у большинства площадок
выпадающий список (значение — сам текст статуса), у nistp — чекбоксы
``trade_state[]``. Номер страницы — скрытое поле формы ``pagenum``.

Листинги у площадок группы разные — ``table.data`` или ``table.node_view``,
ссылка на торги в ``<a href>`` или в ``onclick`` строки, строка на торги или на
лот, колонки в разном порядке. Одинакова только ссылка на торги
``trade_view.php?trade_nid=N``: по ней листинг сводится к торгам, а колонки
находятся по заголовку. Страница торгов у всех одна: пары
``<td>подпись</td><td>значение</td>``, лоты — таблицы с заголовком «Лот № N».

Разбор перенесён из справочника, регулярные выражения заменены на XPath и
строковые операции. Площадки — ``tp.ruson_platforms``, запуск — ``tp.run_ruson``.
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

#: Поле статуса в форме листинга: ``trade_state`` или ``trade_state[]``.
STATUS_FIELD = "trade_state"
KNOWN_STATUSES = [
    "Торги объявлены",
    "Прием заявок",
    "Прием заявок завершен",
    "Идут торги",
    "Подведение итогов",
    "Торги завершены",
    "Торги не состоялись",
    "Торги приостановлены",
    "Торги отменены",
]
#: Актуальные по умолчанию: торги объявлены или идёт приём заявок.
ACTIVE = "Торги объявлены,Прием заявок"

#: Заголовки колонок листинга — части слов, в разных написаниях площадок.
COLUMNS = {
    "status": ("состояние", "статус"),
    "deadline": ("конец приема", "окончание приема", "окончания представ"),
    "organizer": ("организатор",),
    "debtor": ("должник",),
}
TRADE_VIEW = "trade_view.php?trade_nid="


def digits(text: str | None) -> str:
    """Ведущие цифры строки: «70700-ОТПП» -> «70700»."""
    return "".join(takewhile(str.isdigit, text or ""))


# ── листинг ──────────────────────────────────────────────────────────────────


def header(page: Selector) -> list[str]:
    """Заголовки колонок таблицы торгов — строка с наибольшим числом ``<th>``.

    Над таблицей у rus_on и promkonsalt стоит строка поиска со своим ``<th>``;
    считать все ``<th>`` страницы подряд значило бы сдвинуть номера колонок.
    """
    rows = page.xpath("//tr[th]")
    if not rows:
        return []
    widest = max(rows, key=lambda row: len(row.xpath("./th")))
    return [(clean(th.xpath("string(.)").get()) or "").lower() for th in widest.xpath("./th")]


def trade_code(text: str) -> str | None:
    """Видимый код торгов в строке: «70700-ОТПП» — цифры, дефис, от двух заглавных."""
    for word in text.split():
        head, _, tail = word.partition("-")
        letters = "".join(takewhile(str.isupper, tail))
        if head.isdigit() and len(letters) >= 2:
            return f"{head}-{letters}"
    return None


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Страница листинга -> торги, без повторов внутри страницы (по ``trade_nid``).

    ``trade_id`` — цифры видимого кода торгов, если он есть, иначе внутренний
    ``trade_nid``. Сведения из колонок приблизительные: авторитетные берутся со
    страницы торгов.
    """
    headers = header(page)
    cols = {
        name: next((i for i, h in enumerate(headers) if any(n in h for n in needles)), None)
        for name, needles in COLUMNS.items()
    }
    trades = []
    seen: set[str] = set()
    rows = page.xpath(
        f'//tr[.//a[contains(@href, "{TRADE_VIEW}")]] | //tr[contains(@onclick, "{TRADE_VIEW}")]'
    )
    for row in rows:
        href = row.xpath(f'.//a[contains(@href, "{TRADE_VIEW}")]/@href').get()
        nid = digits((href or row.xpath("./@onclick").get() or "").split(TRADE_VIEW, 1)[-1])
        if not nid or nid in seen:
            continue
        seen.add(nid)
        cells = row.xpath("./td")

        def cell(name: str, cells: list[Selector] = cells) -> Selector | None:
            index = cols[name]
            return cells[index] if index is not None and index < len(cells) else None

        code = trade_code(clean(row.xpath("string(.)").get()) or "")
        debtor = cell("debtor")
        trades.append(
            {
                "trade_nid": nid,
                "trade_id": digits(code) if code else nid,
                "trade_number": code,
                "trade_type": code.split("-")[1] if code else None,
                # onclick без href: ссылка относительно листинга — там же, где он.
                "detail_url": href or f"trade_view.php?trade_nid={nid}",
                "status": clean(cell("status").xpath("string(.)").get()) if cell("status") else None,
                "bidding_date": clean(cell("deadline").xpath("string(.)").get())
                if cell("deadline")
                else None,
                "organizer": clean(cell("organizer").xpath("string(.)").get()) if cell("organizer") else None,
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(debtor.xpath('.//span[contains(@style, "bold")][1]/text()').get())
                if debtor
                else None,
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Следующий номер из пейджера ``pagenum_send(N)``; ``None`` — страница последняя."""
    numbers = (
        page.xpath('//ul[contains(@class, "pagination")]//a/@onclick[contains(., "pagenum_send(")]')
        .xpath('substring-before(substring-after(., "pagenum_send("), ")")')
        .getall()
    )
    later = [int(n) for n in numbers if n.isdigit() and int(n) > num_page]
    return min(later) if later else None


# ── страница торгов ──────────────────────────────────────────────────────────


def field(scope: Selector, label: str) -> str | None:
    """Значение строки, первая ячейка которой содержит ``label``.

    Без привязки к классу: у большинства площадок подпись — ``td.label``, у
    promkonsalt — простой ``td``.
    """
    return clean(
        scope.xpath(f'.//tr[td[1][contains(normalize-space(.), "{label}")]]/td[2]').xpath("string(.)").get()
    )


def block(page: Selector, title: str) -> Selector:
    """Таблица раздела с заголовком ``title``; берётся самый внутренний элемент с этим
    текстом, иначе попалась бы внешняя таблица всей страницы."""
    node = page.xpath(
        f'//*[contains(normalize-space(.), "{title}")][not(.//*[contains(normalize-space(.), "{title}")])]'
    )
    return node.xpath("./ancestor::table[1]")


def debtor_of(page: Selector) -> str | None:
    """Должник из раздела «Информация о должнике»: ФИО или полное наименование."""
    section = block(page, "Информация о должнике")
    if not section:
        return None
    if "юридич" in (field(section, "Тип должника") or "").lower():
        return field(section, "Полное наименование") or field(section, "Наименование должника")
    names = (field(section, "Фамилия"), field(section, "Имя"), field(section, "Отчество"))
    return " ".join(p for p in names if p) or None


def organizer_of(page: Selector) -> str | None:
    """Организатор из «Информации об организаторе», иначе — его контактное лицо (promkonsalt)."""
    section = block(page, "Информация об организаторе")
    organizer = field(section, "Наименование") if section else None
    if not organizer and (contact := block(page, "Контактное лицо организатора")):
        organizer = field(contact, "ФИО")
    return organizer


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Разделы «Лот № N» страницы торгов -> лоты.

    Маркер лота — ``<th>`` или ``span.lot_title`` (promkonsalt), и только самый
    внутренний: фраза «Лот № 1» встречается и в тексте объявления, и без этого
    условия получался лот-призрак без цены.
    """
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "status": field(page, "Статус торгов") or trade.get("status"),
        "bids_end": field(page, "Дата окончания представления") or trade.get("bidding_date"),
        "auction_date": field(page, "Дата проведения"),
        # Колонки листинга на части площадок пустые или захватывают список
        # лотов — раздел страницы торгов надёжнее.
        "organizer": organizer_of(page) or trade.get("organizer"),
        "debtor": debtor_of(page) or trade.get("debtor"),
    }
    markers = page.xpath(
        '//*[(self::th or contains(@class, "lot_title")) and contains(., "Лот №")'
        ' and not(descendant::*[contains(., "Лот №")])]'
    )
    lots = []
    for marker in markers:
        title = clean(marker.xpath("string(.)").get()) or ""
        lot_num = digits(title.split("Лот №", 1)[1].strip())
        if not lot_num:
            continue
        table = marker.xpath("./ancestor::table[1]")
        detail = {
            label.rstrip(":").strip(): value
            for row in table.xpath(".//tr[td[2]]")
            if (label := clean(row.xpath("string(./td[1])").get()))
            and (value := clean(row.xpath("string(./td[2])").get()))
        }
        lots.append(
            {
                **shared,
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "lot_num": lot_num,
                "description": field(table, "Наименование")
                or (title.split(":", 1)[1].strip() if ":" in title else None),
                "price": field(table, "Начальная цена"),
                "detail": detail,
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class TenderRuson(Crawler):
    """Наследнику-площадке достаточно задать ``name`` и ``DOMAIN``; путь листинга у части свой."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "bankrot/trade_list.php"

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
        return listing_request(self, action, fields, "pagenum", 1, {"search": index})

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
            yield listing_request(self, action, fields, "pagenum", next_page, {"search": index})
        elif index + 1 < len(self.searches):
            yield self.search(index + 1)

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по айтему на лот. Своей страницы у лота нет — его адрес
        это адрес торгов."""
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
    return replace(TenderRuson.settings, **overrides)
