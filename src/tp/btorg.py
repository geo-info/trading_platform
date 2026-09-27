"""TenderBtorg — обход площадок на движке btorg (edoc-ETP).

В листинге ``/etp/trade/list.html?page=N`` строка на торги, но цен нет: лоты и
цены — в AJAX-фрагменте торгов, за которым заходим с признаком XHR. Обход в
два уровня: страница листинга -> фрагмент лотов каждых торгов -> по айтему на
лот. Разметка — в ``tp.marking.btorg``.

Окно ``since`` на btorg не действует: в листинге нет срока приёма заявок, а
остановка по его началу теряла бы торги, начатые раньше окна и ещё идущие.

Новая площадка — модуль в ``tp.platforms.btorg``::

    class Atctrade(TenderBtorg):
        name = "atctrade"
        DOMAIN = "https://atctrade.ru"
"""

from __future__ import annotations

from typing import Any, ClassVar

from collector import Crawler, Response

from tp.common import BASE_SETTINGS, CrawlParams, check_status, lot_item, paging_stops
from tp.marking.btorg import find_next_page, parse_listing, parse_lots

#: Фрагмент лотов отдаётся только на AJAX-запрос.
XHR = {"X-Requested-With": "XMLHttpRequest"}


class TenderBtorg(Crawler):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "etp/trade/list.html"

    settings = BASE_SETTINGS
    params = CrawlParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга выводится из домена; у базы движка домена нет.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Листинг: зайти за лотами каждых торгов и шагнуть на следующую страницу."""
        check_status(response)
        page = response.selector()
        num_page = response.metadata.get("page", 1)
        trades = parse_listing(page)
        await self.log(f"{response.status} | страница {num_page} | торгов {len(trades)}")

        for trade in trades:
            yield response.follow(
                trade["lots_url"], callback=self.parse_trade, metadata={"trade": trade}, headers=XHR
            )

        # Срока приёма заявок в листинге нет — окно по дате не действует.
        if await paging_stops(self, num_page, None):
            return
        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
            return
        yield self.request(f"{self.start_urls[0]}?page={next_page}", metadata={"page": next_page})

    async def parse_trade(self, response: Response) -> Any:
        """Фрагмент лотов торгов: по айтему на лот."""
        check_status(response)
        trade = response.metadata["trade"]
        lots = parse_lots(response.selector(), trade)
        await self.log(f"{response.status} | торги {trade['trade_id']} | лотов {len(lots)}")
        for lot in lots:
            # Без номера лота документ нечем ключевать в хранилище.
            if lot.get("lot_id"):
                yield lot_item(self.name, response.request.url, lot)
