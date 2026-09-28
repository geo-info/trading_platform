"""Поиск по статусу через GET-форму листинга — общее для Kendo, btorg и rus-on.

У этих движков фильтр статуса — поле обычной GET-формы: выпадающий список
(Kendo ``status_id``, btorg ``processStatus``, большинство rus-on
``trade_state``) или чекбоксы (nistp ``trade_state[]``). Коды статусов у
площадок одного движка бывают разными — у Kendo «Объявлен» где 3, где 2, —
поэтому статус задаётся *названием*, а значение для запроса берётся из формы
самой площадки.

Поля формы собирает та же чистая функция фреймворка, что стоит за
``Response.form_request()``: запрос выглядит так, как его отправил бы браузер.
Следующая страница — те же поля плюс номер страницы.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from collector.crawler.form import form_request as form_fields
from parsel import Selector

from core.help import clean
from core.conf import settings as config


@dataclass(frozen=True)
class SearchParams:
    """Что задаётся на прогон: статусы (названия через запятую) и предел страниц на статус."""

    statuses: str = ""
    max_pages: int = config.parsing.max_pages


def norm(text: str) -> str:
    """Название статуса для сравнения: без регистра, «ё» и лишних пробелов."""
    return " ".join(text.lower().replace("ё", "е").split())


def split_statuses(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def check_statuses(value: str, known: list[str]) -> list[str]:
    """Названия статусов прогона; незнакомое — ошибка до первого запроса."""
    names = split_statuses(value)
    allowed = {norm(name) for name in known}
    if unknown := [name for name in names if norm(name) not in allowed]:
        raise ValueError(f"незнакомые статусы {unknown}; известные: {', '.join(known)}")
    return names


@dataclass(frozen=True)
class StatusChoice:
    """Статус в форме площадки: название, имя поля и значение для запроса."""

    label: str
    field: str
    value: str


def status_choices(page: Selector, field: str) -> dict[str, StatusChoice]:
    """Варианты поля статуса на странице: нормализованное название -> выбор.

    ``<option>`` без атрибута ``value`` браузер отправляет своим текстом — так
    устроен список rus-on, — и здесь так же. У чекбокса название — его value.
    """
    choices: dict[str, StatusChoice] = {}
    for select in page.xpath(f'//select[starts-with(@name, "{field}")]'):
        for option in select.xpath("./option"):
            label = clean(option.xpath("string(.)").get()) or ""
            value = option.attrib.get("value", label)
            if label and value:
                choices[norm(label)] = StatusChoice(label, select.attrib["name"], value)
    for box in page.xpath(f'//input[@type="checkbox"][starts-with(@name, "{field}")]'):
        value = box.attrib.get("value", "")
        if value:
            choices[norm(value)] = StatusChoice(value, box.attrib["name"], value)
    return choices


def search_fields(page: Selector, url: str, choice: StatusChoice) -> tuple[str, list[tuple[str, str]]]:
    """Адрес и поля GET-формы, в которой лежит поле статуса, с выбранным статусом.

    Форм на странице бывает несколько (вход, поиск), поэтому берётся та, что
    содержит поле статуса. Прежние значения поля статуса — отмеченные по
    умолчанию чекбоксы — снимаются: ищем ровно по одному статусу.
    """
    form = page.xpath(f'//form[.//*[@name="{choice.field}"]]')
    action, _, fields = form_fields(Selector(text=form.get()), url)
    return action, [(name, value) for name, value in fields if name != choice.field] + [
        (choice.field, choice.value)
    ]


def listing_request(
    crawler: Any,
    action: str,
    fields: list[tuple[str, str]],
    page_param: str,
    num_page: int,
    metadata: dict[str, Any],
) -> Request:
    """Страница ``num_page`` выдачи поиска: поля формы плюс номер страницы.

    У rus-on номер страницы — скрытое поле самой формы (``pagenum``), его
    пейджер и заполняет; значит, подставлять номер в него, а не дописывать
    второй такой же параметр.
    """
    params = fields
    if num_page > 1:
        params = [(name, value) for name, value in fields if name != page_param] + [
            (page_param, str(num_page))
        ]
    return crawler.request(
        action, params=params, callback=crawler.parse_listing, metadata={**metadata, "page": num_page}
    )


def check_status(response: Response) -> None:
    """Не-200 — ошибка запроса, а не пустая страница: иначе площадка с
    переехавшим листингом выглядела бы обходом без лотов."""
    if response.status != 200:
        raise ValueError(f"{response.status} для {response.request.url}")
