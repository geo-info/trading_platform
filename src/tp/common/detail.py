"""Детальный парсер: лоты, ждущие деталей, -> запросы -> детали.

Какие лоты обходить, решает база, а не парсер: новые (деталей ещё нет) и
изменившиеся после них — см. ``Store.pending_detail``. Список парсер берёт
из хранилища, которое ему передаёт ``open_run`` (``ctx.sink``); записывает
детали раннер — как и лоты листинга.

Детали лежат на странице лота (iTender) или на странице торгов, общей для
её лотов (Kendo, btorg, rus-on; у лота тогда есть ``trade_url``). Лоты с
общей страницей идут одним запросом: фреймворк всё равно отбросил бы
повторный запрос на тот же адрес, и лот остался бы без деталей.

Площадка своя у каждого лота, со своими особенностями (хук, TLS,
сертификат), поэтому детальный парсер — не отдельная иерархия, а примесь к
классу площадки: ``detail_of(Alfalot, ITenderDetail)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, ClassVar

from collector import Crawler, Request, Response
from parsel import Selector

from tp.common.site import check_status


@dataclass(frozen=True)
class DetailParams:
    """Что задаётся на прогон деталей.

    ``limit`` — сколько лотов за прогон: первый прогон по всей базе был бы
    долгим. ``statuses`` — только лоты с этими статусами (как их пишет
    листинг), через запятую; пусто — все.
    """

    limit: int = 100
    statuses: str = ""


class Detail(Crawler):
    """Примесь: вместо листинга — страницы лотов, ждущих деталей.

    Движок задаёт ``parse_details(page, lot_ids)`` -> ``{lot_id: detail}`` и,
    если страница отдаётся не на простой GET, ``DETAIL_HEADERS``.
    """

    DETAIL_HEADERS: ClassVar[dict[str, str] | None] = None

    params = DetailParams()

    @staticmethod
    def parse_details(page: Selector, lot_ids: list[str]) -> dict[str, Any]:
        raise NotImplementedError

    async def start_requests(self) -> AsyncIterator[Request]:
        statuses = [s.strip() for s in self.params.statuses.split(",") if s.strip()] or None
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit, statuses)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        for url, lot_ids in group_by_page(lots).items():
            yield self.request(url, headers = self.DETAIL_HEADERS, metadata = {"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        check_status(response)
        lot_ids = response.metadata["lot_ids"]
        details = self.parse_details(response.selector(), lot_ids)
        if missing := [lot_id for lot_id in lot_ids if lot_id not in details]:
            await self.log(f"{response.request.url}: нет лотов {missing}")
        for lot_id, detail in details.items():
            yield {"lot_id": lot_id, "detail": detail}


def group_by_page(lots: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Адрес страницы с деталями -> ``lot_id`` её лотов: ``trade_url``, иначе ``lot_url``."""
    groups: dict[str, list[str]] = defaultdict(list)
    for lot in lots:
        groups[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
    return dict(groups)


def detail_of(platform: type[Crawler], mixin: type[Detail]) -> type[Detail]:
    """Детальный парсер площадки: её имя и настройки, разбор — примеси движка.

    Модуль — площадки: путь к своему сертификату фреймворк ищет от файла класса.
    """
    return type(f"{platform.__name__}Detail", (mixin, platform), {"__module__": platform.__module__})
