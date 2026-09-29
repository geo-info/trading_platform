"""Базовый парсер движка rus-on.

Поиск по статусу — GET-форма листинга (см. ``tp.common.StatusSearch``). Поле
статуса — ``trade_state``: у большинства площадок выпадающий список (значение
— сам текст статуса), у nistp — чекбоксы ``trade_state[]``. Номер страницы —
скрытое поле формы ``pagenum``.

Листинги у площадок группы разные — ``table.data`` или ``table.node_view``,
ссылка на торги в ``<a href>`` или в ``onclick`` строки, строка на торги или на
лот, колонки в разном порядке. Одинакова только ссылка на торги
``trade_view.php?trade_nid=N``: по ней листинг сводится к торгам, а колонки
находятся по заголовку. Страница торгов у всех одна: пары
``<td>подпись</td><td>значение</td>``, лоты — таблицы с заголовком «Лот № N».

Площадка наследует ``Ruson`` и задаёт ``name`` и ``DOMAIN``; путь листинга у
части площадок свой (``LISTING_PATH``).
"""

from __future__ import annotations

from itertools import takewhile
from typing import Any

from collector import Request, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits
from core.lot import Lot
from tp.common import SearchParams, StatusSearch, check_status

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
    "bids_end": ("конец приема", "окончание приема", "окончания представ"),
    "organizer": ("организатор",),
    "debtor": ("должник",),
}
TRADE_VIEW = "trade_view.php?trade_nid="


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

        def text(name: str) -> str | None:
            node = cell(name)
            return clean(node.xpath("string(.)").get()) if node is not None else None

        code = trade_code(clean(row.xpath("string(.)").get()) or "")
        debtor = cell("debtor")
        trades.append(
            {
                "trade_nid": nid,
                "trade_id": digits(code) if code else nid,
                "trade_number": code,
                "trade_type": code.split("-")[1] if code else None,
                # onclick без href: ссылка относительно листинга — там же, где он.
                "trade_url": href or f"{TRADE_VIEW}{nid}",
                "status": text("status"),
                "bids_end": text("bids_end"),
                "organizer": text("organizer"),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(debtor.xpath('.//span[contains(@style, "bold")][1]/text()').get())
                if debtor is not None
                else None,
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Следующий номер из пейджера ``pagenum_send(N)``; ``None`` — страница последняя."""
    onclicks = page.xpath('//ul[contains(@class, "pagination")]//a/@onclick').getall()
    numbers = [onclick.partition("pagenum_send(")[2].partition(")")[0] for onclick in onclicks]
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


def pairs_of(table: Selector) -> dict[str, str]:
    """Пары «подпись: значение» строк таблицы."""
    return {
        label.rstrip(":").strip(): value
        for row in table.xpath(".//tr[td[2]]")
        if (label := clean(row.xpath("string(./td[1])").get()))
        and (value := clean(row.xpath("string(./td[2])").get()))
    }


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


def lot_tables(page: Selector) -> list[tuple[str, str, Selector]]:
    """Разделы «Лот № N» страницы торгов: номер лота, заголовок, таблица.

    Маркер лота — ``<th>`` или ``span.lot_title`` (promkonsalt), и только самый
    внутренний: фраза «Лот № 1» встречается и в тексте объявления, и без этого
    условия получался лот-призрак без цены.
    """
    markers = page.xpath(
        '//*[(self::th or contains(@class, "lot_title")) and contains(., "Лот №")'
        ' and not(descendant::*[contains(., "Лот №")])]'
    )
    tables = []
    for marker in markers:
        title = clean(marker.xpath("string(.)").get()) or ""
        if lot_num := digits(title.split("Лот №", 1)[1].strip()):
            tables.append((lot_num, title, marker.xpath("./ancestor::table[1]")))
    return tables


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Лоты страницы торгов; сведения о торгах — со страницы, листинг — запасной."""
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "status": field(page, "Статус торгов") or trade.get("status"),
        "bids_end": field(page, "Дата окончания представления") or trade.get("bids_end"),
        "auction_date": field(page, "Дата проведения"),
        # Колонки листинга на части площадок пустые или захватывают список
        # лотов — раздел страницы торгов надёжнее.
        "organizer": organizer_of(page) or trade.get("organizer"),
        "debtor": debtor_of(page) or trade.get("debtor"),
    }
    return [
        {
            **shared,
            "lot_id": f"{trade['trade_id']}_{lot_num}",
            "lot_num": lot_num,
            "description": field(table, "Наименование")
            or (title.split(":", 1)[1].strip() if ":" in title else None),
            "price": field(table, "Начальная цена"),
        }
        for lot_num, title, table in lot_tables(page)
    ]


# ── краулер ──────────────────────────────────────────────────────────────────


class Ruson(StatusSearch):

    LISTING_PATH = "bankrot/trade_list.php"
    STATUS_FIELD = "trade_state"
    PAGE_PARAM = "pagenum"

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
        """Страница торгов: по айтему на лот. Своей страницы у лота нет — его адрес
        это адрес торгов."""
        check_status(response)
        url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            yield Lot(source = self.name, lot_url = url, trade_url = url, **lot).model_dump()
