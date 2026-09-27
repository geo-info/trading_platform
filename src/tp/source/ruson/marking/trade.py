"""Разметка страницы торгов rus-on: разделы должника и организатора, лоты.

Страница у всех площадок одна: пары ``<td>подпись</td><td>значение</td>``,
лоты — таблицы с заголовком «Лот № N». В coll-temp в дату торгов клали
начало приёма заявок; теперь это «Дата проведения», если она есть.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean, parse_price

_LOT_NUM_RE = re.compile(r"Лот № ?(\d+)")


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
