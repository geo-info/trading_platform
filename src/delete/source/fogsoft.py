"""TenderFogsoft — площадки банкротных торгов на движке iTender (Fogsoft).

Лоты собираются по статусам, которые задаёт прогон (параметр ``statuses``):
поиск со статусом -> перелистывание до последней страницы -> поиск со
следующим статусом. Статус в форме поиска — одиночный выпадающий список,
поэтому на каждый статус свой поиск. Поиски идут строго друг за другом, а не
вперемешку: если сервер держит условия поиска в сессии, чередование страниц
двух поисков смешало бы их выдачу.

С каждой строки выдачи — заход на страницу лота: её разделы разбираются в
``detail`` — легенда раздела -> пары «подпись: значение».

Площадки — наследники в ``tp.fogsoft_platforms``, запуск — ``tp.run_fogsoft``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.help import clean
from core.conf import settings as config

#: Статусы — value в списке «Статус» формы поиска. Коды одинаковы на всех
#: площадках движка; tendergarant и utender пишут «Приём» через «ё».
STATUSES = {
    "5": "Извещение опубликовано",
    "7": "Прием заявок",
    "14": "Прием заявок на интервале не активен",
    "8": "Определение участников торгов",
    "1": "Идут торги",
    "15": "Подведение результатов",
    "2": "Окончен",
    "3": "Не состоялся",
    "4": "Отменён организатором",
    "13": "Приостановлен",
}

#: Актуальные по умолчанию: торги объявлены или идёт приём заявок. «Прием
#: заявок на интервале не активен» — публичное предложение между интервалами
#: снижения цены: приём откроется на следующем, уже по меньшей цене.
ACTIVE = "5,7,14"


def resolve_statuses(value: str) -> list[str]:
    """``"7"``, ``"Прием заявок"`` или ``"5,7,14"`` -> коды статусов.

    Название сравнивается без учёта регистра и «ё»; незнакомый статус — ошибка
    до первого запроса, а не молча пустой обход.
    """
    by_name = {name.lower().replace("ё", "е"): code for code, name in STATUSES.items()}
    codes = []
    for part in (p.strip() for p in value.split(",")):
        code = part if part in STATUSES else by_name.get(part.lower().replace("ё", "е"))
        if code is None:
            known = ", ".join(f"{c} — {n}" for c, n in STATUSES.items())
            raise ValueError(f"незнакомый статус {part!r}; известные: {known}")
        codes.append(code)
    return codes


@dataclass(frozen=True)
class FogsoftParams:
    """Что задаётся на прогон: какие статусы собирать и предел страниц на статус."""

    #: Коды или названия статусов через запятую, см. ``STATUSES``.
    statuses: str = ACTIVE
    #: Предохранитель: сколько страниц выдачи листать на один статус.
    max_pages: int = config.parsing.max_pages


#: Список «Статус» и кнопка поиска — внутри панели поиска.
STATUS_SELECT = '//select[contains(@name, "purchaseStatusID")]/@name'
#: У utender кнопка называется btnSearch, у остальных площадок — SearchButton.
SEARCH_BUTTON = (
    '//input[@type="submit"][contains(@name, "SearchButton") or contains(@name, "btnSearch")]/@name'
)

#: Разделы страницы лота, которые к лоту не относятся. Форма загрузки документа
#: выглядит как раздел с подписями, и отсеять её по пустоте нельзя: звёздочка
#: обязательного поля в «Тип документа ( * )» читается как значение «*».
SKIP_SECTIONS = frozenset({"Информация о документе"})


def current_page(page: Selector) -> int | None:
    """Номер текущей страницы — единственный номер пейджера без ссылки."""
    number = page.xpath('(//td[@class="pager"])[1]/span[number(.) = number(.)]/text()').get()
    return int(number) if number else None


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


def parse_rows(page: Selector) -> list[dict[str, Any]]:
    """Строки таблицы листинга.

    Разбор идёт по номерам ячеек, а не по заголовкам: заголовок — это текст
    для человека, его переформулируют, не трогая разметку.
    """
    rows = []
    for tr in page.xpath('//tr[@class="gridRow"]'):
        cells = tr.xpath("./td")
        if len(cells) < 11:
            continue
        rows.append(
            {
                "lot_url": clean(tr.xpath(".//a[contains(@href,'/lots/view/')]/@href").get()),
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


class TenderFogsoft(Crawler):
    """Наследнику-площадке достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "public/purchases-all/"

    settings = Settings(
        concurrency=1, delay=config.parsing.delay, timeout=config.parsing.http_timeout, max_errors=50
    )
    params = FogsoftParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга выводится из домена; у базы движка домена нет.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def opened(self) -> None:
        """Коды статусов прогона — до первого запроса: незнакомый статус не ходит в сеть."""
        self.codes = resolve_statuses(self.params.statuses)

    async def parse(self, response: Response) -> Any:
        """Стартовая страница: начать с поиска по первому статусу прогона."""
        yield self.search(response, 0)

    def search(self, response: Response, index: int) -> Any:
        """Отправить форму поиска со статусом ``self.codes[index]``.

        Кнопка называется явно: в форме WebForms вся страница, и первая кнопка
        в ней — «Войти», а не «Искать торги».
        """
        page = response.selector()
        return response.form_request(
            formdata={page.xpath(STATUS_SELECT).get(): self.codes[index]},
            click=page.xpath(SEARCH_BUTTON).get(),
            callback=self.parse_listing,
            metadata={"status": index, "page": 1},
        )

    async def parse_listing(self, response: Response) -> Any:
        """Страница выдачи поиска: строки, затем следующая страница или следующий статус."""
        page = response.selector()
        index, num_page = response.metadata["status"], response.metadata["page"]
        status = STATUSES[self.codes[index]]
        rows = parse_rows(page)
        await self.log(f"«{status}»: страница {current_page(page) or 1}, строк {len(rows)}")

        for row in rows:
            if row["lot_url"]:
                yield response.follow(
                    row["lot_url"],
                    callback=self.parse_lot,
                    metadata={"row": {**row, "searched_status": status}},
                )

        next_target = find_next_target(page, num_page)
        if next_target is not None and num_page < self.params.max_pages:
            yield response.form_request(
                formdata={"__EVENTTARGET": next_target, "__EVENTARGUMENT": ""},
                callback=self.parse_listing,
                metadata={"status": index, "page": num_page + 1},
            )
        elif index + 1 < len(self.codes):
            # Выдача этого статуса кончилась — форма поиска есть и на ней.
            yield self.search(response, index + 1)

    async def parse_lot(self, response: Response) -> Any:
        """Страница лота: строка листинга плюс разделы страницы."""
        url = response.request.url
        yield {
            "source": self.name,
            # Номер лота — последний сегмент адреса /lots/view/<номер>/.
            "lot_id": url.rstrip("/").rsplit("/", 1)[-1],
            "url": url,
            "fetched_at": datetime.now(UTC).isoformat(),
            **response.metadata["row"],
            "detail": parse_detail(response.selector()),
        }


def narrow(**overrides: Any) -> Settings:
    """Настройки площадки: общие плюс её особенность (хук, сертификат, TLS)."""
    return replace(TenderFogsoft.settings, **overrides)
