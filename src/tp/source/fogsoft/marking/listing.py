"""Разметка листинга iTender: строки таблицы, пейджер, форма поиска.

Листинг — ASP.NET WebForms, одна форма на всю страницу. Строки лотов — ``tr.gridRow``,
ссылки пейджера — ``__doPostBack``, фильтры — выпадающие списки панели поиска.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean


def find_next_target(page: Selector, num_page: int) -> str | None:
    """EVENTTARGET следующей страницы; ``None`` — текущая последняя.

    Номер и ``>>`` ищутся одним запросом, потому что ``.get()`` берёт первую
    ссылку по документу, а в пейджере номера всегда стоят раньше ``>>``.
    Значит переход на следующий блок срабатывает ровно тогда, когда нужного
    номера в текущем блоке нет. Ссылка ``<<`` под предикат не подходит.
    """
    next_num, block = f'normalize-space()="{num_page + 1}"', 'normalize-space()=">>"'
    href = page.xpath(f'(//td[@class="pager"])[1]//a[{next_num} or {block}]/@href').get()
    match = re.search(r"__doPostBack\('([^']+)'", href or "")
    return match.group(1) if match else None


#: Поля формы поиска над листингом: у всех площадок движка они внутри
#: раскрывающейся панели, и её id входит в имя каждого поля.
SEARCH_PANEL = "phExpandCollapse"


def filter_resets(page: Selector) -> dict[str, str]:
    """Выпадающие списки формы поиска, где выбрано не «Все», -> значение «Все».

    Площадка может открывать листинг с фильтром по умолчанию: centerr
    показывает только «Прием заявок», и без сброса в базу не попадает ни один
    завершённый лот. Сбрасываем не только статус, а любой список с вариантом
    «Все», — какой фильтр выставит следующая площадка, заранее не знать.
    Список без «Все» — не фильтр, его не трогаем. Пустой словарь — сбрасывать
    нечего.
    """
    resets: dict[str, str] = {}
    for select in page.xpath(f"//select[contains(@name, '{SEARCH_PANEL}')]"):
        first = select.xpath("./option[1]")
        if clean(first.xpath("string(.)").get()) != "Все":
            continue
        everything = first.attrib.get("value", "")
        chosen = select.xpath("./option[@selected]/@value").get()
        if chosen is not None and chosen != everything:
            resets[select.attrib["name"]] = everything
    return resets


def search_button(page: Selector) -> str | None:
    """Имя кнопки поиска. Она стоит в панели первой, перед «Очистить»."""
    return page.xpath(f"//input[@type='submit'][contains(@name, '{SEARCH_PANEL}')][1]/@name").get()


def parse_rows(page: Selector) -> list[dict[str, Any]]:
    """Строки таблицы листинга.

    Разбор идёт по номерам ячеек, а не по заголовкам: заголовок — это текст
    для человека, его переформулируют, не трогая разметку.
    """
    rows = []
    for tr in page.xpath('//tr[@class="gridRow"]'):
        cells = tr.xpath("./td")
        if len(cells) < 11:
            continue
        rows.append(
            {
                "lot_url": clean(tr.xpath(".//a[contains(@href,'/lots/view/')]/@href").get()),
                "trade_id": clean(cells[0].xpath("string(.)").get()),
                "auction_name": clean(cells[1].xpath("string(.)").get()),
                "lot_num": clean(cells[2].xpath("string(.)").get()),
                "description": clean(cells[3].xpath("string(.)").get()),
                "price": clean(cells[4].xpath("string(.)").get()),
                "organizer": clean(cells[5].xpath("string(.)").get()),
                "bids_end": clean(cells[6].xpath("string(.)").get()),
                "auction_date": clean(cells[7].xpath("string(.)").get()),
                "status": clean(cells[8].xpath("string(.)").get()),
                "winner": clean(cells[9].xpath("string(.)").get()),
                "trade_type": clean(cells[10].xpath("string(.)").get()),
            }
        )
    return rows


def has_viewstate(page: Selector) -> bool:
    """На странице есть токены формы, без которых следующую страницу не взять."""
    return bool(page.xpath("//input[@name='__CVIEWSTATE']/@value").get())
