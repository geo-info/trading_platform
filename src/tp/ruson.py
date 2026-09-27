"""TenderRuson — площадки банкротных торгов на движке rus-on.

Листинги у площадок группы разные: таблица ``table.data`` или
``table.node_view``, ссылка на торги в ``<a href>`` или в ``onclick`` строки,
строка на торги или на лот. Колонки стоят в разном порядке. Одинакова только
ссылка на торги — ``trade_view.php?trade_nid=N``, — поэтому листинг сводится
к торгам по ней, а колонки находятся по заголовку. Страница торгов у всех
одна: пары ``<td>подпись</td><td>значение</td>``, лоты — таблицы с заголовком
«Лот № N».

Пейджер — JavaScript ``pagenum_send(N)``; страница N берётся GET-ом
``?pagenum=N`` — проверено: вторая страница не повторяет первую.

Разбор перенесён из coll-temp (``collector/sources/ruson``) с исправлениями:

- колонки нумеровались по всем ``<th>`` страницы, а у rus_on и promkonsalt
  над таблицей стоит строка поиска со своим ``<th>`` — номера съезжали на
  одну. Заголовки берутся из строки с наибольшим числом ``<th>``;
- в дату торгов клали *начало* приёма заявок; теперь это «Дата проведения»,
  если она на странице есть;
- срок приёма заявок читается и из листинга — по нему работает окно ``since``.

Новая площадка::

    class Nistp(TenderRuson):
        name = "nistp"
        DOMAIN = "https://nistp.ru"
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from parsel import Selector

from core.parsing import clean, parse_price
from tp.dive import DiveCrawler

_NID_RE = re.compile(r"trade_view\.php\?trade_nid=(\d+)")
_REF_RE = re.compile(r"(/?[^'\"\s]*trade_view\.php\?trade_nid=\d+)")
_CODE_RE = re.compile(r"(\d+)-[А-Я]{2,}")
_PAGENUM_RE = re.compile(r"pagenum_send\((\d+)\)")
_LOT_NUM_RE = re.compile(r"Лот № ?(\d+)")

#: Заголовки колонок листинга — части слов, в разных написаниях площадок.
STATUS = ("состояние", "статус")
DEADLINE = ("конец приема", "окончание приема", "окончания представ")
ORGANIZER = ("организатор",)
DEBTOR = ("должник",)


# ── листинг ──────────────────────────────────────────────────────────────────


def header(page: Selector) -> list[str]:
    """Заголовки колонок таблицы торгов — строка с наибольшим числом ``<th>``.

    Над таблицей у части площадок стоит строка поиска со своим ``<th>``;
    считать все ``<th>`` страницы подряд значило бы сдвинуть номера колонок.
    """
    rows = page.xpath("//tr[th]")
    if not rows:
        return []
    widest = max(rows, key=lambda row: len(row.xpath("./th")))
    return [(clean(th.xpath("string(.)").get()) or "").lower() for th in widest.xpath("./th")]


def column(headers: list[str], needles: tuple[str, ...]) -> int | None:
    """Номер колонки, заголовок которой содержит любую из ``needles``."""
    return next((i for i, text in enumerate(headers) if any(n in text for n in needles)), None)


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Страница листинга -> торги, без повторов внутри страницы (по ``trade_nid``).

    ``trade_id`` — цифры видимого кода торгов, если он есть, иначе внутренний
    ``trade_nid``. Сведения из колонок приблизительные: авторитетные берутся
    со страницы торгов.
    """
    headers = header(page)
    cols = {
        name: column(headers, needles)
        for name, needles in {
            "status": STATUS,
            "deadline": DEADLINE,
            "organizer": ORGANIZER,
            "debtor": DEBTOR,
        }.items()
    }
    trades: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in page.xpath(
        '//tr[.//a[contains(@href, "trade_view.php")]] | //tr[contains(@onclick, "trade_view.php")]'
    ):
        ref = row.xpath('.//a[contains(@href, "trade_view.php")]/@href').get()
        if not ref and (onclick := _REF_RE.search(row.xpath("./@onclick").get() or "")):
            ref = onclick.group(1)
        nid = _NID_RE.search(ref or "")
        if not nid or nid.group(1) in seen:
            continue
        seen.add(nid.group(1))
        cells = row.xpath("./td")

        def cell(name: str, cells: list[Selector] = cells) -> str | None:
            index = cols[name]
            return (
                clean(cells[index].xpath("string(.)").get())
                if index is not None and index < len(cells)
                else None
            )

        code = _CODE_RE.search(clean(row.xpath("string(.)").get()) or "")
        debtor_index = cols["debtor"]
        debtor = None
        if debtor_index is not None and debtor_index < len(cells):
            # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
            debtor = clean(cells[debtor_index].xpath('.//span[contains(@style, "bold")][1]/text()').get())
        trades.append(
            {
                "trade_nid": nid.group(1),
                "trade_id": code.group(1) if code else nid.group(1),
                "trade_number": code.group(0) if code else None,
                "trade_type": clean(code.group(0).split("-")[1]) if code else None,
                "detail_url": ref,
                "status": cell("status"),
                "bidding_date": cell("deadline"),
                "organizer": cell("organizer"),
                "debtor": debtor,
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Следующий номер из пейджера ``pagenum_send(N)``; ``None`` — страница последняя."""
    pages = [
        int(n)
        for onclick in page.xpath('//ul[contains(@class, "pagination")]//a/@onclick').getall()
        for n in _PAGENUM_RE.findall(onclick)
    ]
    later = [p for p in pages if p > num_page]
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
    """Таблица раздела с заголовком ``title`` — «Информация о должнике» и т. п.

    Берётся самый внутренний элемент с этим текстом, иначе попалась бы
    внешняя таблица всей страницы.
    """
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
    return (
        " ".join(
            p for p in (field(section, "Фамилия"), field(section, "Имя"), field(section, "Отчество")) if p
        )
        or None
    )


def organizer_of(page: Selector) -> str | None:
    """Организатор из «Информации об организаторе», иначе — его контактное лицо.

    Часть площадок (promkonsalt) раздела организатора не выводит, только
    «Контактное лицо организатора».
    """
    section = block(page, "Информация об организаторе")
    organizer = field(section, "Наименование") if section else None
    if not organizer and (contact := block(page, "Контактное лицо организатора")):
        organizer = field(contact, "ФИО")
    return organizer


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Разделы «Лот № N» страницы торгов -> лоты.

    Маркер лота — ``<th>`` (у большинства) или ``span.lot_title`` (promkonsalt),
    и только самый внутренний: фраза «Лот № 1» встречается и в тексте
    объявления, и без этого условия получался лот-призрак без цены.
    """
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "lot_url": trade.get("detail_url"),
        "status": field(page, "Статус торгов") or trade.get("status"),
        "bidding_date": field(page, "Дата окончания представления") or trade.get("bidding_date"),
        "event_date": field(page, "Дата проведения"),
        # Колонки листинга на части площадок пустые или захватывают список
        # лотов — раздел страницы торгов надёжнее.
        "organizer": organizer_of(page) or trade.get("organizer"),
        "debtor": debtor_of(page) or trade.get("debtor"),
    }
    markers = page.xpath(
        '//*[(self::th or contains(@class, "lot_title")) and contains(., "Лот №")'
        ' and not(descendant::*[contains(., "Лот №")])]'
    )
    lots: list[dict[str, Any]] = []
    for marker in markers:
        title = clean(marker.xpath("string(.)").get()) or ""
        lot_num = _LOT_NUM_RE.search(title)
        table = marker.xpath("./ancestor::table[1]")
        detail = {
            label.rstrip(":").strip(): value
            for row in table.xpath(".//tr[td[2]]")
            if (label := clean(row.xpath("string(./td[1])").get()))
            and (value := clean(row.xpath("string(./td[2])").get()))
        }
        price_raw = field(table, "Начальная цена")
        lots.append(
            {
                **shared,
                "lot_id": f"{trade['trade_id']}_{lot_num.group(1)}" if lot_num else None,
                "lot_num": lot_num.group(1) if lot_num else None,
                "description": field(table, "Наименование")
                or (title.split(":", 1)[1].strip() if ":" in title else None),
                "price": parse_price(price_raw),
                "price_raw": price_raw,
                "detail": detail,
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class TenderRuson(DiveCrawler):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``; путь листинга у части площадок свой."""

    LISTING_PATH: ClassVar[str] = "bankrot/trade_list.php"
    PAGE_PARAM: ClassVar[str] = "pagenum"

    def list_trades(self, page: Selector) -> list[dict[str, Any]]:
        return parse_listing(page)

    def next_page(self, page: Selector, num_page: int) -> int | None:
        return find_next_page(page, num_page)

    def extract_lots(self, page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
        return parse_lots(page, trade)
