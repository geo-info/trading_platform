"""Базовый парсер движка iTender (он же Fogsoft).

Листинг ``public/purchases-all/``, пейджер — ASP.NET ``__doPostBack``.
Площадка наследует ``ITender`` и задаёт ``name`` и ``DOMAIN``; особенность
(хук, сертификат, TLS) — ``settings = narrow(ITender, ...)``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from collector import Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean
from tp.common.site import Site, check_status


def parse_rows(page: Selector) -> list[dict[str, Any]]:
    """Строки таблицы листинга.

    Разбор идёт по номерам ячеек, а не по заголовкам: заголовок — это текст
    для человека, его переформулируют, не трогая разметку.
    """
    rows = []
    for tr in page.xpath('//tr[@class="gridRow"]'):
        cells = tr.xpath("./td")
        lot_url = clean(tr.xpath(".//a[contains(@href,'/lots/view/')]/@href").get())

        if len(cells) < 11 or not lot_url:
            continue

        rows.append(
            {
                "lot_url": lot_url,
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


def find_next_target(page: Selector, num_page: int) -> str | None:
    """EVENTTARGET следующей страницы; ``None`` — текущая последняя.

    Номер и ``>>`` ищутся одним запросом, потому что первая подходящая ссылка
    по документу — номер, а он в пейджере всегда стоит раньше ``>>``. Значит
    переход на следующий блок срабатывает ровно тогда, когда нужного номера в
    текущем блоке нет. Ссылка ``<<`` под предикат не подходит.
    """
    next_num, block = f'normalize-space()="{num_page + 1}"', 'normalize-space()=">>"'
    link = page.xpath(f'(//td[@class="pager"])[1]//a[{next_num} or {block}][1]')
    target = link.xpath('substring-before(substring-after(@href, "__doPostBack(\'"), "\'")').get()
    return target or None


@dataclass(frozen=True)
class ITenderParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class ITender(Site):

    LISTING_PATH = "public/purchases-all/"

    # Площадка сужает их через ``narrow(ITender, ...)``: alfalot, например,
    # за проверкой inprotect ходит в один поток.
    settings = Settings(
        concurrency = 5,
        delay = 0.5,
        timeout = 60.0,
        max_errors = 50,
    )
    params = ITenderParams()

    async def parse(self, response: Response) -> Any:
        check_status(response)
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        rows = parse_rows(page)
        await self.log(f"страница {num_page}: лотов {len(rows)}")

        for row in rows:
            yield self.make_item(row, response)

        next_target = find_next_target(page, num_page)
        if next_target is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            yield response.form_request(
                formdata = {"__EVENTTARGET": next_target, "__EVENTARGUMENT": ""},
                metadata = {"num_page": num_page + 1},
            )

    def make_item(self, row: dict[str, Any], response: Response) -> dict[str, Any]:
        """Лот: полная ссылка и ``lot_id`` — последний сегмент её пути."""
        lot_url = response.urljoin(row["lot_url"])
        return {
            "source": self.name,
            "lot_id": lot_url.rstrip("/").rsplit("/", 1)[-1],
            **row,
            "lot_url": lot_url,
        }
