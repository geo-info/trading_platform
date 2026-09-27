"""TenderBtorg — площадки банкротных торгов на движке btorg (edoc-ETP).

Листинг ``/etp/trade/list.html?page=N`` — ``table.data``, строка на торги:
номер, организатор, должник с предметом торгов, состояние, начало приёма
заявок. Цен в листинге нет, поэтому в каждые торги заходим за
AJAX-фрагментом лотов ``inner-view-lots.html`` — по ``table.data`` на лот
(``id="lotNumberN"``) с парами «подпись — значение» и, у публичного
предложения, вложенной таблицей интервалов снижения цены. Страницы — в
windows-1251; перекодирует их фреймворк по заголовку ответа.

Разбор перенесён из coll-temp (``collector/sources/btorg``) с двумя
исправлениями:

- дату из листинга coll-temp клал в срок приёма заявок, а это его *начало*;
  срок у публичного предложения — конец последнего интервала, у аукциона во
  фрагменте его нет;
- строки вложенной таблицы интервалов попадали в ``extra`` с датами вместо
  подписей — теперь интервалы разобраны в ``price_schedule``.

Окно ``since`` на btorg не действует: в листинге нет срока приёма заявок, а
остановка по его началу теряла бы торги, начатые раньше окна и ещё идущие.

Новая площадка::

    class Atctrade(TenderBtorg):
        name = "atctrade"
        DOMAIN = "https://atctrade.ru"
"""

from __future__ import annotations

import re
from typing import Any, ClassVar

from parsel import Selector

from core.parsing import clean, parse_price
from tp.dive import DiveCrawler

_PAGE_RE = re.compile(r"page=(\d+)")
_DIGITS_RE = re.compile(r"\d+")
_ID_RE = re.compile(r"id=(\d+)")
_LOT_NUM_RE = re.compile(r"lotNumber(\d+)")

#: AJAX-фрагмент с лотами торгов — с ценами, которых нет в листинге.
LOTS_PATH = "/etp/trade/inner-view-lots.html"


# ── листинг ──────────────────────────────────────────────────────────────────


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Строки ``table.data`` -> торги.

    Внутренний id торгов, по которому запрашиваются лоты, — в ``onclick``
    строки (``…general.html?id=NNN…``), видимого номера для этого мало.
    """
    trades: list[dict[str, Any]] = []
    for row in page.xpath('//table[@class="data"]//tr[@onclick]'):
        purchase = _ID_RE.search(row.xpath("./@onclick").get() or "")
        cells = row.xpath("./td")
        if not purchase or len(cells) < 5:
            continue
        number = clean(cells[0].xpath("string(.)").get())
        digits = _DIGITS_RE.search(number or "")
        if not number or not digits:
            continue
        parts = number.split("-")
        trades.append(
            {
                "trade_id": digits.group(0),
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "organizer": clean(cells[1].xpath("string(.)").get()),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(cells[2].xpath('.//div[contains(@style, "bold")]//text()').get()),
                "status": clean(cells[3].xpath("string(.)").get()),
                "bids_start": clean(cells[4].xpath("string(.)").get()),
                "lots_url": f"{LOTS_PATH}?perspective=inline&id={purchase.group(1)}",
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Наименьший номер в пейджере больше текущего; ``None`` — страница последняя."""
    pages = [
        int(match.group(1))
        for href in page.xpath('//a[contains(@href, "list.html?page=")]/@href').getall()
        if (match := _PAGE_RE.search(href))
    ]
    later = [p for p in pages if p > num_page]
    return min(later) if later else None


# ── лоты торгов ──────────────────────────────────────────────────────────────


def property_details(detail: dict[str, str]) -> str | None:
    """«Сведения об имуществе должника…» — описание лота, где «Предмет торгов» не заполнен.

    Ищется по вхождению: первая «С» в подписи на части площадок латинская.
    """
    return next((value for label, value in detail.items() if "ведения об имуществе" in label), None)


def parse_schedule(lot: Selector) -> list[dict[str, str]]:
    """Интервалы снижения цены публичного предложения: строка -> {заголовок: ячейка}."""
    table = lot.xpath('.//table[contains(@class, "inner")]')
    headers = [clean(td.xpath("string(.)").get()) or "" for td in table.xpath(".//tr[1]/*")]
    schedule: list[dict[str, str]] = []
    for row in table.xpath(".//tr[position() > 1]"):
        cells = [clean(td.xpath("string(.)").get()) or "" for td in row.xpath("./td")]
        if headers and len(cells) == len(headers):
            schedule.append(dict(zip(headers, cells, strict=True)))
    return schedule


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Таблицы ``lotNumberN`` фрагмента -> лоты; сведения о торгах — из листинга."""
    lots: list[dict[str, Any]] = []
    for lot in page.xpath('//table[contains(@id, "lotNumber")]'):
        lot_num = _LOT_NUM_RE.search(lot.xpath("./@id").get() or "")
        # Только свои строки таблицы лота — строки вложенной таблицы интервалов
        # дали бы в extra подписи-даты.
        own_rows = lot.xpath(".//tr[td[2]][ancestor::table[1][contains(@id, 'lotNumber')]]")
        detail = {
            label.rstrip(":").strip(): value
            for row in own_rows
            if (label := clean(row.xpath("string(./td[1])").get()))
            and (value := clean(row.xpath("string(./td[2])").get()))
        }
        schedule = parse_schedule(lot)
        price_raw = detail.get("Начальная цена продажи имущества")
        lots.append(
            {
                "lot_id": f"{trade['trade_id']}_{lot_num.group(1)}" if lot_num else None,
                "trade_id": trade["trade_id"],
                "trade_number": trade.get("trade_number"),
                "trade_type": trade.get("trade_type"),
                "lot_num": lot_num.group(1) if lot_num else None,
                "debtor": trade.get("debtor"),
                "organizer": trade.get("organizer"),
                "lot_url": trade.get("lots_url"),
                "description": detail.get("Предмет торгов") or property_details(detail),
                "price": parse_price(price_raw),
                "price_raw": price_raw,
                "status": detail.get("Статус торгов") or trade.get("status"),
                # Срок приёма публичного предложения — конец последнего интервала.
                "bidding_date": schedule[-1].get("Дата окончания приема заявок") if schedule else None,
                "detail": {**detail, "Начало приема заявок": trade.get("bids_start")},
                "price_schedule": schedule,
            }
        )
    return lots


# ── краулер ──────────────────────────────────────────────────────────────────


class TenderBtorg(DiveCrawler):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``."""

    LISTING_PATH: ClassVar[str] = "etp/trade/list.html"
    DIVE_URL_KEY: ClassVar[str] = "lots_url"
    DIVE_HEADERS: ClassVar[dict[str, str] | None] = {"X-Requested-With": "XMLHttpRequest"}
    DEADLINE_KEY: ClassVar[str | None] = None

    def list_trades(self, page: Selector) -> list[dict[str, Any]]:
        return parse_listing(page)

    def next_page(self, page: Selector, num_page: int) -> int | None:
        return find_next_page(page, num_page)

    def extract_lots(self, page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
        return parse_lots(page, trade)
