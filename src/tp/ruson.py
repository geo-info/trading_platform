"""TenderRuson — обход площадок на движке rus-on.

Листинг сводится к торгам по ссылке ``trade_view.php``, а лоты и цены — на
странице торгов. Обход в два уровня: страница листинга -> заход в каждые торги
-> по айтему на лот. Пейджер — JavaScript ``pagenum_send(N)``, страница
берётся GET-ом ``?pagenum=N``. Разметка — в ``tp.marking.ruson``.

Новая площадка — модуль в ``tp.platforms.ruson``; путь листинга у части
площадок свой::

    class Sistematorg(TenderRuson):
        name = "sistematorg"
        DOMAIN = "https://sistematorg.com"
        LISTING_PATH = "tradelist.php"
"""

from __future__ import annotations

from typing import Any, ClassVar

from collector import Crawler, Response

from tp.common import BASE_SETTINGS, CrawlParams, check_status, lot_item, paging_stops
from tp.marking.ruson import find_next_page, parse_listing, parse_lots


class TenderRuson(Crawler):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "bankrot/trade_list.php"

    settings = BASE_SETTINGS
    params = CrawlParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга выводится из домена; у базы движка домена нет.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Листинг: зайти в каждые торги и шагнуть на следующую страницу."""
        check_status(response)
        page = response.selector()
        num_page = response.metadata.get("page", 1)
        trades = parse_listing(page)
        await self.log(f"{response.status} | страница {num_page} | торгов {len(trades)}")

        for trade in trades:
            yield response.follow(trade["detail_url"], callback=self.parse_trade, metadata={"trade": trade})

        if await paging_stops(self, num_page, [t["bidding_date"] for t in trades]):
            return
        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
            return
        yield self.request(f"{self.start_urls[0]}?pagenum={next_page}", metadata={"page": next_page})

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по айтему на лот."""
        check_status(response)
        trade = response.metadata["trade"]
        lots = parse_lots(response.selector(), trade)
        await self.log(f"{response.status} | торги {trade['trade_id']} | лотов {len(lots)}")
        for lot in lots:
            # Без номера лота документ нечем ключевать в хранилище.
            if lot.get("lot_id"):
                yield lot_item(self.name, response.request.url, lot)
