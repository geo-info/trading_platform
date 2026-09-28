"""Детальный парсер iTender: страница лота -> разделы с парами «подпись: значение».

Какие лоты обходить, решает база, а не парсер: новые (деталей ещё нет) и
изменившиеся после них — см. ``MongoStorage.pending_detail``. Список парсер
берёт из хранилища, которое ему передаёт ``open_run`` (``ctx.sink``);
записывает детали раннер — как и лоты листинга.

Площадка своя у каждого лота, со своими особенностями (хук inprotect,
TLS, сертификат), поэтому детальный парсер — не отдельная иерархия, а
примесь к классу площадки: ``detail_of(Alfalot)``.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from core.help import clean
from tp.itender.base import ITender

#: Разделы, в которых нет сведений о лоте.
SKIP_SECTIONS = frozenset({"Информация о документе"})


def cell(node: Selector) -> str | None:
    """Текст ячейки мимо ссылок.

    Рядом с ценой сидит рекламная кнопка «Купить с агентом», и без этого она
    приклеивается к сумме.
    """
    return clean(" ".join(node.xpath(".//text()[not(ancestor::a)]").getall()))


def value_of(node: Selector) -> str | list[str] | None:
    """Значение ячейки ``tdContent``: текст или, если внутри грид, — список его строк.

    Классификатор ЕФРСБ с несколькими классами — грид; склеенный в строку, он
    даёт «Жилые здания (помещения) Земельные участки», и обратно не разделить.
    """
    rows = node.xpath(".//tr[contains(@class,'gridRow') or contains(@class,'gridAltRow')]")
    if rows:
        return [text for row in rows if (text := cell(row))]
    return cell(node)


def parse_detail(page: Selector) -> dict[str, dict[str, str | list[str] | None]]:
    """Разделы страницы лота: легенда -> пары «подпись: значение».

    Значение берётся из соседней ячейки своей подписи, а не сводится с
    подписями двумя списками по порядку: в вёрстке есть ячейки-распорки
    ``tdContent`` без подписи (tendergarant, utender), и при сведении по порядку
    всё ниже распорки съезжает на одну подпись.
    """
    sections: dict[str, dict[str, str | list[str] | None]] = {}
    for fieldset in page.xpath("//fieldset[legend]"):
        legend = clean(fieldset.xpath("./legend/text()").get())
        if not legend:
            continue
        # Номер в конце легенды («Информация о лоте №1») у каждого лота свой.
        legend = legend.split("№")[0].strip()
        if legend in SKIP_SECTIONS:
            continue
        pairs: dict[str, str | list[str] | None] = {}
        for title in fieldset.xpath(".//td[@class='tdTitle']"):
            # strip после rstrip: у части подписей пробел перед двоеточием.
            label = (cell(title) or "").rstrip(":").strip()
            value = title.xpath("following-sibling::td[1][@class='tdContent']")
            if label and value:
                pairs[label] = value_of(value[0])
        if any(pairs.values()):
            sections[legend] = pairs
    return sections


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class ITenderDetail(ITender):
    """Примесь: вместо листинга — страницы лотов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        for lot in lots:
            yield self.request(lot["lot_url"], metadata = {"lot_id": lot["lot_id"]})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        yield {"lot_id": response.metadata["lot_id"], "detail": parse_detail(response.selector())}


def detail_of(platform: type[ITender]) -> type[ITenderDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы лота.

    Модуль — площадки: путь к своему сертификату фреймворк ищет от файла
    класса.
    """
    return type(f"{platform.__name__} Detail", (ITenderDetail, platform), {"__module__": platform.__module__})
