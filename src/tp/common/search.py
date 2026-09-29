"""Поиск по статусу GET-формой листинга — общее для Kendo, btorg и rus-on.

Фильтр статуса у этих движков — поле обычной GET-формы листинга:
выпадающий список (Kendo ``status_id``, btorg ``processStatus``, rus-on
``trade_state``) или чекбоксы (nistp ``trade_state[]``). Коды статусов у
площадок одного движка бывают разными — у Kendo «Объявлен» где 3, где 2, —
поэтому статус задаётся *названием*, а значение для запроса берётся из формы
самой площадки. Обход: поиск со статусом -> перелистывание -> поиск со
следующим статусом.

Листинг перечисляет торги, а лоты — только на странице торгов, поэтому с
каждой строки заход в торги (``StatusSearch.trade_request``).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from collector import Request, Response
from collector.crawler.form import form_request as form_fields
from parsel import Selector

from core.conf import conf
from core.help import clean
from tp.common.site import Site, check_status


@dataclass(frozen=True)
class SearchParams:
    """Что задаётся на прогон: статусы (названия через запятую) и предел страниц на статус."""

    statuses: str = ""
    max_pages: int = conf.parsing.max_pages


def norm(text: str) -> str:
    """Название статуса для сравнения: без регистра, «ё» и лишних пробелов."""
    return " ".join(text.lower().replace("ё", "е").split())


def split_statuses(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


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


def page_fields(fields: list[tuple[str, str]], page_param: str, num_page: int) -> list[tuple[str, str]]:
    """Поля формы для страницы ``num_page`` выдачи.

    У rus-on номер страницы — скрытое поле самой формы (``pagenum``), его
    пейджер и заполняет; значит, подставлять номер в него, а не дописывать
    второй такой же параметр.
    """
    if num_page == 1:
        return fields
    return [(name, value) for name, value in fields if name != page_param] + [(page_param, str(num_page))]


class StatusSearch(Site):
    """Листинг по статусам: поиск -> страницы выдачи -> заход в каждые торги.

    Движок задаёт путь листинга (``LISTING_PATH``), поле статуса
    (``STATUS_FIELD``), параметр страницы (``PAGE_PARAM``), разбор выдачи
    (``parse_listing``, ``find_next_page``) и заход в торги (``trade_request``)
    со своим ``parse_trade``. Площадке достаточно ``name`` и ``DOMAIN``.
    """

    STATUS_FIELD: ClassVar[str]
    PAGE_PARAM: ClassVar[str] = "page"

    params = SearchParams()

    @staticmethod
    def parse_listing(page: Selector) -> list[dict[str, Any]]:
        """Строки выдачи -> торги."""
        raise NotImplementedError

    @staticmethod
    def find_next_page(page: Selector, num_page: int) -> int | None:
        """Номер следующей страницы выдачи; ``None`` — текущая последняя."""
        raise NotImplementedError

    def trade_request(self, response: Response, trade: dict[str, Any]) -> Request:
        """Запрос страницы торгов (или фрагмента с лотами) с ``trade`` в метаданных."""
        raise NotImplementedError

    async def parse(self, response: Response) -> Any:
        """Стартовая страница: найти в форме статусы прогона и начать с первого."""
        check_status(response)
        page = response.selector()
        choices = status_choices(page, self.STATUS_FIELD)
        self.searches = []
        for name in split_statuses(self.params.statuses):
            if (choice := choices.get(norm(name))) is None:
                await self.log(f"статуса «{name}» в форме площадки нет — пропускаю")
                continue
            self.searches.append((choice, *search_fields(page, response.request.url, choice)))
        if self.searches:
            yield self.search(0, 1)

    def search(self, index: int, num_page: int) -> Request:
        """Страница ``num_page`` выдачи поиска ``self.searches[index]``."""
        _, action, fields = self.searches[index]
        return self.request(
            action,
            params=page_fields(fields, self.PAGE_PARAM, num_page),
            callback=self.search_page,
            metadata={"search": index, "page": num_page},
        )

    async def search_page(self, response: Response) -> Any:
        """Страница выдачи: зайти в каждые торги, затем следующая страница или статус."""
        check_status(response)
        page = response.selector()
        index, num_page = response.metadata["search"], response.metadata["page"]
        choice = self.searches[index][0]
        trades = self.parse_listing(page)
        await self.log(f"«{choice.label}»: страница {num_page}, торгов {len(trades)}")
        for trade in trades:
            yield self.trade_request(response, trade)

        next_page = self.find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"«{choice.label}»: страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"«{choice.label}»: дошли до предела max_pages={self.params.max_pages}")
            next_page = None
        if next_page is not None:
            yield self.search(index, next_page)
        elif index + 1 < len(self.searches):
            yield self.search(index + 1, 1)
