"""Базовый парсер движка rus-on.

Листинги у площадок группы разные — ``table.data`` или ``table.node_view``,
ссылка на торги в ``<a href>`` или в ``onclick`` строки, строка на торги или на
лот, колонки в разном порядке. Одинакова только ссылка на торги
``trade_view.php?trade_nid=N``: по ней листинг сводится к торгам, а колонки
находятся по заголовку. Номер страницы — параметр ``pagenum`` (пейджер
выставляет его в форме через ``pagenum_send(N)``). Страница торгов у всех одна:
пары ``<td>подпись</td><td>значение</td>``, лоты — таблицы с заголовком
«Лот № N». Своей страницы у лота нет: его адрес — адрес торгов.

Площадка наследует ``Ruson`` и задаёт ``name`` и ``DOMAIN``, при другом пути
листинга — ``LISTING_PATH``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import takewhile
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits, local_href
from core.lot import Lot
from core.registry import register

#: Заголовки колонок листинга — части слов, в разных написаниях площадок.
COLUMNS = {
    "status": ("состояние", "статус"),
    "deadline": ("конец приема", "окончание приема", "окончания представ"),
    "organizer": ("организатор",),
    "debtor": ("должник",),
}
TRADE_VIEW = "trade_view.php?trade_nid="


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
            return clean(node.xpath("string(.)").get()) if node else None

        code = trade_code(clean(row.xpath("string(.)").get()) or "")
        debtor = cell("debtor")
        trades.append(
            {
                "trade_id": digits(code) if code else nid,
                "trade_number": code,
                "trade_type": code.split("-")[1] if code else None,
                # onclick без href: ссылка относительно листинга — там же, где он.
                "trade_url": local_href(href) if href else f"{TRADE_VIEW}{nid}",
                "status": text("status"),
                "bids_end": text("deadline"),
                "organizer": text("organizer"),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(debtor.xpath('.//span[contains(@style, "bold")][1]/text()').get())
                if debtor
                else None,
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Следующий номер из пейджера ``pagenum_send(N)``; ``None`` — страница последняя.

    Номер — регуляркой по значению ``onclick``: XPath поверх выбранного
    атрибута parsel молча возвращает пустоту, и пейджер «кончался» на первой
    странице (так было в прежнем парсере).
    """
    numbers = page.xpath(
        '//ul[contains(@class, "pagination")]//a[contains(@onclick, "pagenum_send(")]/@onclick'
    ).re(r"pagenum_send\((\d+)\)")
    later = [int(n) for n in numbers if int(n) > num_page]
    return min(later) if later else None


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


def lot_tables(page: Selector) -> list[tuple[str, str, Selector]]:
    """Разделы «Лот № N»: номер лота, заголовок раздела и его таблица.

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
        table = marker.xpath("./ancestor::table[1]")
        if (lot_num := digits(title.split("Лот №", 1)[1].strip())) and table:
            tables.append((lot_num, title, table[0]))
    return tables


def lot_pairs(table: Selector) -> dict[str, str]:
    """Пары «подпись: значение» таблицы лота — только её собственные строки.

    Внутри таблицы лота бывает вложенная таблица интервалов снижения цены: её
    строки дали бы пары «дата начала: дата окончания», а строка, в которой она
    лежит, — склеенный текст всей таблицы. График разбирает ``parse_schedule``.
    """
    pairs = {}
    for row in table.xpath(".//tr[td[2]][not(td[2]//table)]"):
        if row.xpath("ancestor::table[1]")[0].root is not table.root:
            continue
        label = clean(row.xpath("string(./td[1])").get())
        value = clean(row.xpath("string(./td[2])").get())
        if label and value:
            pairs[label.rstrip(":").strip()] = value
    return pairs


def parse_schedule(table: Selector) -> list[dict[str, str]]:
    """Интервалы снижения цены из вложенной таблицы лота: строка -> {заголовок: ячейка}."""
    inner = table.xpath('.//table[contains(@class, "discount_int")]')
    headers = [clean(th.xpath("string(.)").get()) or "" for th in inner.xpath(".//tr[1]/*")]
    schedule = []
    for row in inner.xpath(".//tr[td]"):
        cells = [clean(td.xpath("string(.)").get()) or "" for td in row.xpath("./td")]
        if headers and len(cells) == len(headers):
            schedule.append(dict(zip(headers, cells, strict=True)))
    return schedule


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Разделы «Лот № N» страницы торгов -> поля ``Lot`` без ``source`` и адресов."""
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


@dataclass(frozen=True)
class RusonParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class Ruson(Crawler):
    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "bankrot/trade_list.php"

    settings = Settings(
        concurrency=1,
        delay=conf.parsing.delay,
        timeout=conf.parsing.http_timeout,
        max_errors=50,
    )
    params = RusonParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга — из домена площадки. LISTING_PATH у части площадок
        # свой, поэтому пересобираем и тогда, когда задан только он.
        if "DOMAIN" in cls.__dict__ or "LISTING_PATH" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]
        # Площадка — класс, объявивший домен; прочие наследники — примеси.
        if "DOMAIN" in cls.__dict__:
            register(cls)

    async def parse(self, response: Response) -> Any:
        """Страница листинга: зайти в каждые торги, затем следующая страница."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        trades = parse_listing(page)
        await self.log(f"страница {num_page}: торгов {len(trades)}")

        for trade in trades:
            yield response.follow(trade["trade_url"], callback=self.parse_trade, metadata={"trade": trade})

        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            yield self.request(
                self.start_urls[0], params={"pagenum": next_page}, metadata={"num_page": next_page}
            )

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по ``Lot`` на лот; адрес лота — адрес торгов."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        trade_url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            yield Lot(source=self.name, lot_url=trade_url, trade_url=trade_url, **lot).model_dump()
