"""Разметка страницы лота iTender: разделы с подписями, документы, график снижения цены.

Страница собрана из ``<fieldset><legend>…</legend>`` с парами ``td.tdTitle`` /
``td.tdContent``. Подписи сводятся к одному написанию в ``labels``, известные
пары перечислены в ``known_labels``.
"""

from __future__ import annotations

import re
from typing import Any

from parsel import Selector

from core.parsing import clean
from tp.source.fogsoft.marking.labels import canon_detail


def cell(node: Selector) -> str | None:
    """Текст ячейки мимо ссылок.

    Рядом со значением цены сидит рекламная кнопка «Купить с агентом», и без
    этого она приклеивается к сумме. Отбрасываем ссылки целиком: на разобранных
    страницах лотов других ссылок в ячейках значений нет.
    """
    return clean(" ".join(node.xpath(".//text()[not(ancestor::a)]").getall()))


#: Разделы страницы лота, которые к лоту не относятся. Форма загрузки документа
#: выглядит как раздел с подписями, и отсеять её по пустоте нельзя: звёздочка
#: обязательного поля в «Тип документа ( * )» читается как значение «*».
SKIP_SECTIONS = frozenset({"Информация о документе"})


#: Значение ячейки: текст или, если внутри грид, — список его строк.
Value = str | list[str] | None


def value_of(node: Selector) -> Value:
    """Значение ячейки ``tdContent``.

    Ячейка с гридом внутри (классификатор ЕФРСБ) — это список, а не текст: при
    сборке в строку названия классов склеиваются через пробел, и «Жилые здания
    (помещения) Земельные участки» обратно уже не разделить.
    """
    rows = node.xpath(".//tr[contains(@class,'gridRow') or contains(@class,'gridAltRow')]")
    if rows:
        return [text for row in rows if (text := cell(row))]
    return cell(node)


def raw_detail(page: Selector) -> dict[str, dict[str, Value]]:
    """Разделы страницы лота как на площадке: легенда -> пары «подпись: значение».

    Страница собрана из ``<fieldset><legend>…</legend>`` с таблицами внутри,
    где подписи лежат в ``td.tdTitle``, а значения — в следующих ``td.tdContent``.
    Это устойчивее, чем брать таблицы по порядку: вокруг ещё полтора десятка
    таблиц меню и форма входа.

    Значение ищется от своей подписи — соседняя ячейка в той же строке, — а не
    сводится с подписями двумя списками по порядку. В вёрстке встречаются
    ячейки-распорки ``tdContent`` без подписи (tendergarant, utender), и при
    сведении по порядку всё, что ниже распорки, съезжает на одну подпись:
    цена оказывается в «Шаге», счётчик заявок — в «Классификаторе ЕФРСБ».

    Разделы без единого значения отбрасываются: подписи есть, показать нечего.
    """
    sections: dict[str, dict[str, Value]] = {}
    for fieldset in page.xpath("//fieldset[legend]"):
        legend = clean(fieldset.xpath("./legend/text()").get())
        if not legend:
            continue
        # Номер в конце легенды («Информация о лоте №1») отличается у
        # каждого лота, и ключ раздела с ним был бы одноразовым.
        legend = re.sub(r"\s*№\s*\S+\s*$", "", legend)
        if legend in SKIP_SECTIONS:
            continue

        pairs: dict[str, Value] = {}
        for title in fieldset.xpath(".//td[@class='tdTitle']"):
            # strip после rstrip: у части подписей перед двоеточием пробел
            # («…публичного предложения :»), и без него ключ двоится.
            label = (cell(title) or "").rstrip(":").strip()
            value = title.xpath("following-sibling::td[1][@class='tdContent']")
            if label and value:
                pairs[label] = value_of(value[0])

        if any(pairs.values()):
            sections[legend] = pairs

    return sections


def parse_detail(page: Selector) -> dict[str, dict[str, Value]]:
    """Разделы страницы лота, сведённые к одному написанию (см. ``labels``).

    Отказы от договора здесь отброшены — их отдаёт ``canon_detail`` вторым
    значением, и сборка айтема берёт оба сразу.
    """
    return canon_detail(raw_detail(page))[0]


def parse_attachments(page: Selector) -> list[dict[str, Any]]:
    """Документы лота: имя, ссылка, подписан ли электронной подписью."""
    attachments: list[dict[str, Any]] = []
    for row in page.xpath('//tr[contains(@class, "attachment-grid-row")]'):
        link = row.xpath(".//a[@href]")
        name = clean(link.xpath("string(.)").get())
        url = link.xpath("./@href").get()
        if not name and not url:
            continue
        signed = bool(row.xpath('.//*[contains(@class, "certOk")]'))
        attachments.append({"name": name, "url": url, "signed": signed})
    return attachments


def parse_price_schedule(page: Selector) -> list[dict[str, str]]:
    """График снижения цены — есть только у публичного предложения.

    Раздел — грид без пар ``tdTitle``/``tdContent``, поэтому ``parse_detail``
    его не видит, и разбирается он отдельно: строка грида -> {заголовок: ячейка}.
    """
    fieldset = page.xpath('//fieldset[legend[contains(., "Интервалы снижения цены")]]')
    if not fieldset:
        return []
    headers = [
        clean(td.xpath("string(.)").get()) or ""
        for td in fieldset.xpath('(.//tr[contains(@class, "gridHeader")])[1]/td')
    ]
    if not headers:
        return []
    schedule: list[dict[str, str]] = []
    for row in fieldset.xpath('.//tr[contains(@class, "gridRow")]'):
        cells = [clean(td.xpath("string(.)").get()) or "" for td in row.xpath("./td")]
        if len(cells) != len(headers):
            continue
        schedule.append(dict(zip(headers, cells, strict=True)))
    return schedule


#: Раздел страницы, с которым сверяется листинг.
LOT_SECTION = "Информация о лоте"


#: Без этих полей страница лота — не страница лота: разбор промахнулся.
REQUIRED = ("Номер", "Наименование", "Статус", "Начальная цена, руб.", "Классификатор ЕФРСБ")
