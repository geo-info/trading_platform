"""Детальный парсер iTender: страница лота -> разделы с парами «подпись: значение».

Какие лоты обходить, решает база, а как — ``tp.common.detail.Detail``. У лота
iTender своя страница (``lot_url``), так что запрос на лот один.

Детальный парсер — примесь к классу площадки: ``detail_of(Alfalot)``.
"""

from __future__ import annotations

from typing import Any

from parsel import Selector

from core.help import clean
from tp.common.detail import Detail
from tp.common.detail import detail_of as _detail_of
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


class ITenderDetail(Detail):
    """Примесь: вместо листинга — страницы лотов, ждущих деталей."""

    @staticmethod
    def parse_details(page: Selector, lot_ids: list[str]) -> dict[str, Any]:
        # Страница лота — одна на лот: список из одного lot_id.
        return {lot_id: parse_detail(page) for lot_id in lot_ids}


def detail_of(platform: type[ITender]) -> type[ITenderDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы лота."""
    return _detail_of(platform, ITenderDetail)
