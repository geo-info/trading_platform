"""Разметка листинга rus-on: торги по ссылке ``trade_view.php``, колонки по заголовку.

Листинги у площадок группы разные — ``table.data`` или ``table.node_view``,
ссылка в ``<a href>`` или в ``onclick``, строка на торги или на лот, колонки в
разном порядке. Одинакова только ссылка на торги ``trade_view.php?trade_nid=N``.
В coll-temp колонки нумеровались по всем ``<th>`` страницы и у rus_on и
promkonsalt съезжали на одну из-за строки поиска над таблицей.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean

_NID_RE = re.compile(r"trade_view\.php\?trade_nid=(\d+)")


_REF_RE = re.compile(r"(/?[^'\"\s]*trade_view\.php\?trade_nid=\d+)")


_CODE_RE = re.compile(r"(\d+)-[А-Я]{2,}")


_PAGENUM_RE = re.compile(r"pagenum_send\((\d+)\)")


#: Заголовки колонок листинга — части слов, в разных написаниях площадок.
STATUS = ("состояние", "статус")


DEADLINE = ("конец приема", "окончание приема", "окончания представ")


ORGANIZER = ("организатор",)


DEBTOR = ("должник",)


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
