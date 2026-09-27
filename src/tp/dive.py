"""DiveCrawler — листинг торгов, заход в каждые торги, по айтему на лот.

Так устроены три движка из четырёх — Kendo, btorg и rus-on: листинг
перечисляет торги (иногда лоты, но с ссылкой на торги), лоты и их цены лежат
только внутри торгов. Скелет обхода — пагинация, заход, айтем — здесь, а
движок даёт три функции разбора: ``list_trades``, ``next_page`` и
``extract_lots``.

Повторный заход в одни торги — торги, попавшие на две страницы листинга, или
листинг по лотам, где у торгов несколько строк, — отсекает дедупликация
запросов фреймворка: адрес захода у торгов один. В coll-temp для этого
держали своё множество увиденных торгов.

Лот отдаётся моделью ``core.lot.Lot``; лот, который модель не пропустила,
не теряется, а пишется запасным документом (``tp.common.rejected``).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, ClassVar
from urllib.parse import urljoin

from collector import Crawler, Response
from parsel import Selector
from pydantic import ValidationError

from core.lot import Lot
from tp.common import BASE_SETTINGS, CrawlParams, older_than, rejected


class DiveCrawler(Crawler):
    """Площадке достаточно задать ``name`` и ``DOMAIN``; движку — три функции разбора."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = ""
    #: Поле торгов из листинга с адресом, по которому в них заходить.
    DIVE_URL_KEY: ClassVar[str] = "detail_url"
    #: Заголовки захода — например, признак XHR у AJAX-фрагмента btorg.
    DIVE_HEADERS: ClassVar[dict[str, str] | None] = None
    #: Параметр запроса с номером страницы листинга.
    PAGE_PARAM: ClassVar[str] = "page"
    #: Поле торгов из листинга со сроком приёма заявок — по нему работает окно
    #: ``since``. ``None`` — в листинге срока нет, и окно на площадке не действует.
    DEADLINE_KEY: ClassVar[str | None] = "bidding_date"

    settings = BASE_SETTINGS
    params = CrawlParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга выводится из домена, как у площадок iTender. У базы
        # движка домена нет — только у площадки.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    # ── разбор, который даёт движок ─────────────────────────────────────────

    def list_trades(self, page: Selector) -> list[dict[str, Any]]:
        """Страница листинга -> торги (словари с ``DIVE_URL_KEY``)."""
        raise NotImplementedError

    def next_page(self, page: Selector, num_page: int) -> int | None:
        """Номер следующей страницы листинга; ``None`` — страница последняя."""
        raise NotImplementedError

    def extract_lots(self, page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
        """Страница торгов -> лоты: словари полей ``core.lot.Lot``."""
        raise NotImplementedError

    # ── обход ────────────────────────────────────────────────────────────────

    async def parse(self, response: Response) -> Any:
        """Листинг: зайти в каждые торги и шагнуть на следующую страницу."""
        page = response.selector()
        num_page = response.metadata.get("page", 1)
        trades = self.list_trades(page)
        await self.log(f"{response.status} | страница {num_page} | торгов {len(trades)}")

        for trade in trades:
            if url := trade.get(self.DIVE_URL_KEY):
                yield response.follow(
                    url, callback=self.parse_trade, metadata={"trade": trade}, headers=self.DIVE_HEADERS
                )

        if num_page >= self.params.max_pages:
            await self.log(f"остановка: предел max_pages={self.params.max_pages}")
            return

        since = self.params.since
        if (
            since is not None
            and self.DEADLINE_KEY
            and older_than([t.get(self.DEADLINE_KEY) for t in trades], since)
        ):
            await self.log(f"остановка: вся страница {num_page} закрыла приём заявок до {since}")
            return

        next_page = self.next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
            return
        yield self.request(
            f"{self.start_urls[0]}?{self.PAGE_PARAM}={next_page}", metadata={"page": next_page}
        )

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по айтему на лот."""
        trade = response.metadata["trade"]
        lots = self.extract_lots(response.selector(), trade)
        await self.log(f"{response.status} | торги {trade.get('trade_id')} | лотов {len(lots)}")
        for lot in lots:
            # Без номера лота документ нечем ключевать в хранилище.
            if lot.get("lot_id"):
                yield dive_item(self.name, response.request.url, lot)


def dive_item(source: str, page_url: str, lot: dict[str, Any]) -> dict[str, Any]:
    """Айтем лота через модель; не пропущенный моделью — запасным документом."""
    fetched_at = datetime.now(UTC).isoformat()
    # У лота своя страница есть не на всех движках — тогда адрес лота это
    # адрес его торгов.
    url = urljoin(page_url, lot["lot_url"]) if lot.get("lot_url") else page_url
    data = {key: value for key, value in lot.items() if key != "_source"}
    try:
        return Lot.model_validate(
            {**data, "source": source, "url": url, "fetched_at": fetched_at}
        ).model_dump()
    except ValidationError as exc:
        return rejected(source, str(lot["lot_id"]), url, fetched_at, lot, exc)
