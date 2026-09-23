"""Базовый парсер площадок на движке iTender (Fogsoft).

Шестнадцать площадок на этом движке отличаются друг от друга доменом и парой
настроек — вёрстка у них одна. Поэтому разбор, пагинация и обход живут здесь,
а модуль площадки — это её имя, адрес и то, чем она особенная.

Обход в два уровня: листинг даёт строку таблицы и ссылку на лот, страница лота
— подробности. Айтем отдаётся один на лот, уже со сведениями обеих страниц.

Пагинация: ссылки пейджера — не href, а ``__doPostBack``, и страница N+1
берётся POST-ом, который несёт токены страницы N. Цепочку нельзя
распараллелить и нельзя начать с середины — ``concurrency`` обязан остаться
единицей.

Ходим **обычными postback-ами**, без заголовка ``X-MicrosoftAjax``. Тогда
сервер отвечает целой HTML-страницей, а не дельтой UpdatePanel (``text/plain``
с записями ``длина|тип|имя|значение|``), и скрытые поля на каждом шаге лежат
там же, где на первом, — в тегах ``input``. Одна форма ответа на весь обход,
одна функция для токенов, никаких развилок по номеру страницы.

Новая площадка::

    class Centerr(TenderFogsoft):
        name = "centerr"
        DOMAIN = "https://bankrupt.centerr.ru"
"""

from __future__ import annotations

import asyncio
import logging
import re
import sys
from dataclasses import replace
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from collector import Parser, Response, Settings, open_crawler
from parsel import Selector

from core.db import MongoStore
from core.lot import Lot
from core.parsing import parse_datetime, parse_price
from core.settings import settings as config

#: Настройки HTTP, общие для всех площадок движка. Площадка со своей
#: особенностью narrows их через ``replace`` — см. arbbitlot и meta_invest.
#:
#: concurrency остаётся единицей, и это измерено, а не осторожность: площадка
#: обрабатывает наши запросы по одному, поэтому латентность растёт ровно
#: пропорционально числу воркеров, а запросов в секунду не прибавляется.
BASE_SETTINGS = Settings(concurrency=1, delay=config.delay, timeout=config.http_timeout)


# ── разбор ───────────────────────────────────────────────────────────────────


def clean(value: str | None) -> str | None:
    """Схлопнуть пробелы и неразрывные пробелы; пустая строка — это ``None``."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip() or None


def cell(node: Selector) -> str | None:
    """Текст ячейки мимо ссылок.

    Рядом со значением цены сидит рекламная кнопка «Купить с агентом», и без
    этого она приклеивается к сумме. Отбрасываем ссылки целиком: на разобранных
    страницах лотов других ссылок в ячейках значений нет.
    """
    return clean(" ".join(node.xpath(".//text()[not(ancestor::a)]").getall()))


def extract_initial_tokens(page: Selector) -> tuple[str | None, str | None]:
    """``(__CVIEWSTATE, __EVENTVALIDATION)`` из скрытых полей формы."""
    return (
        page.xpath('//input[@id="__CVIEWSTATE"]/@value').get(),
        page.xpath('//input[@id="__EVENTVALIDATION"]/@value').get(),
    )


def find_next_target(page: Selector, num_page: int) -> str | None:
    """EVENTTARGET следующей страницы; ``None`` — текущая последняя.

    Номер и ``>>`` ищутся одним запросом, потому что ``.get()`` берёт первую
    ссылку по документу, а в пейджере номера всегда стоят раньше ``>>``.
    Значит переход на следующий блок срабатывает ровно тогда, когда нужного
    номера в текущем блоке нет. Ссылка ``<<`` под предикат не подходит.
    """
    next_num, block = f'normalize-space()="{num_page + 1}"', 'normalize-space()=">>"'
    href = page.xpath(f'(//td[@class="pager"])[1]//a[{next_num} or {block}]/@href').get()
    match = re.search(r"__doPostBack\('([^']+)'", href or "")
    return match.group(1) if match else None


def build_payload(target: str, cviewstate: str, eventvalidation: str) -> dict[str, str]:
    """Тело POST, повторяющее клик по ссылке пейджера."""
    return {
        "__EVENTTARGET": target,
        "__EVENTARGUMENT": "",
        "__CVIEWSTATE": cviewstate,
        "__EVENTVALIDATION": eventvalidation,
    }


#: Поля формы поиска над листингом: у всех площадок движка они внутри
#: раскрывающейся панели, и её id входит в имя каждого поля.
SEARCH_PANEL = "phExpandCollapse"


def filter_reset_payload(page: Selector) -> dict[str, str] | None:
    """Тело POST формы поиска со сброшенными фильтрами; ``None`` — сбрасывать нечего.

    Площадка может открывать листинг с фильтром по умолчанию: centerr
    показывает только «Прием заявок», и без сброса в базу не попадает ни один
    завершённый лот. Сбрасываем не только статус, а любой выпадающий список,
    где выбрано не «Все», — какой фильтр выставит следующая площадка, заранее
    не знать.
    """
    selects = page.xpath(f"//select[contains(@name, '{SEARCH_PANEL}')]")
    fields: dict[str, str] = {}
    filtered = False
    for select in selects:
        first = select.xpath("./option[1]")
        if clean(first.xpath("string(.)").get()) != "Все":
            # Список без варианта «Все» — не фильтр, его не трогаем.
            fields[select.attrib["name"]] = select.xpath("./option[@selected]/@value").get() or ""
            continue
        everything = first.attrib.get("value", "")
        chosen = select.xpath("./option[@selected]/@value").get()
        filtered |= chosen is not None and chosen != everything
        fields[select.attrib["name"]] = everything
    if not filtered:
        return None

    # Кнопка поиска стоит в панели первой, перед «Очистить».
    button = page.xpath(f"//input[@type='submit'][contains(@name, '{SEARCH_PANEL}')][1]")
    if not button:
        return None
    hidden = {
        node.attrib["name"]: node.attrib.get("value", "")
        for node in page.xpath("//input[@type='hidden'][@name]")
    }
    text = {
        node.attrib["name"]: node.attrib.get("value", "")
        for node in page.xpath(f"//input[not(@type) or @type='text'][contains(@name, '{SEARCH_PANEL}')]")
    }
    return {
        **hidden,
        **text,
        **fields,
        "__EVENTTARGET": "",
        "__EVENTARGUMENT": "",
        button[0].attrib["name"]: button[0].attrib.get("value", ""),
    }


def page_is_older(rows: list[dict[str, Any]], since: date) -> bool:
    """Все лоты страницы закрыли приём заявок раньше ``since`` — дальше листать незачем.

    Листинг отсортирован по номеру торгов, то есть по публикации, а даты
    публикации в нём нет. Ближайшая замена — срок приёма заявок: он растёт
    вместе с номером, хоть и не строго (у публичного предложения интервалы
    тянутся месяцами). Поэтому останавливаемся не на первой старой строке, а
    когда старая вся страница. Строки без даты решения не принимают.
    """
    deadlines = [d.date() for row in rows if (d := parse_datetime(row["bids_end"]))]
    return bool(deadlines) and max(deadlines) < since


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


def parse_detail(page: Selector) -> dict[str, dict[str, Value]]:
    """Разделы страницы лота: легенда -> пары «подпись: значение».

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
            label = (cell(title) or "").rstrip(":")
            value = title.xpath("following-sibling::td[1][@class='tdContent']")
            if label and value:
                pairs[label] = value_of(value[0])

        if any(pairs.values()):
            sections[legend] = pairs

    return sections


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


# ── парсер ───────────────────────────────────────────────────────────────────


class TenderFogsoft(Parser):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "public/purchases-all/"
    #: Предохранитель обхода. Без потолка ошибка в пагинации крутится вечно.
    MAX_PAGES: ClassVar[int] = config.max_pages
    #: Окно обхода по дате, см. ``Settings.since`` и ``page_is_older``.
    SINCE: ClassVar[date | None] = config.since

    settings = BASE_SETTINGS

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # start_urls выводится из домена, чтобы не повторять путь листинга
        # в каждом из шестнадцати модулей.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Листинг: раздать запросы на страницы лотов и шагнуть на следующую."""
        page = response.selector()
        num_page = response.metadata.get("page", 1)

        if num_page == 1 and not response.metadata.get("filters_reset"):
            payload = filter_reset_payload(page)
            if payload is not None:
                # Строки этой страницы отфильтрованы — их не берём: та же первая
                # страница придёт заново уже без фильтра.
                await self.log("листинг открылся с фильтром — сбрасываю")
                yield self.request(
                    response.request.url,
                    method="POST",
                    data=payload,
                    metadata={"page": 1, "filters_reset": True},
                )
                return

        rows = parse_rows(page)
        await self.log(f"{response.status} | страница {num_page} | лотов {len(rows)}")

        for row in rows:
            if row["lot_url"]:
                yield response.follow(row["lot_url"], callback=self.parse_lot, metadata={"row": row})

        if num_page >= self.MAX_PAGES:
            await self.log(f"остановка: предел MAX_PAGES={self.MAX_PAGES}")
            return

        if self.SINCE is not None and page_is_older(rows, self.SINCE):
            await self.log(f"остановка: вся страница {num_page} закрыла приём заявок до {self.SINCE}")
            return

        next_target = find_next_target(page, num_page)
        if next_target is None:
            await self.log(f"страница {num_page} последняя")
            return

        cviewstate, eventvalidation = extract_initial_tokens(page)
        if not cviewstate or not eventvalidation:
            # Молча выйти здесь — значит выдать обрыв цепочки за её конец.
            await self.log(f"страница {num_page}: токенов нет, дальше идти нечем")
            return

        yield self.request(
            response.request.url,
            method="POST",
            data=build_payload(next_target, cviewstate, eventvalidation),
            metadata={"page": num_page + 1},
        )

    async def parse_lot(self, response: Response) -> Any:
        """Страница лота: слить строку листинга с подробностями в один айтем.

        Айтем собирается моделью ``core.lot.Lot``: она типизирует цену и сроки
        листинга, а разделы страницы кладёт в ``extra`` как есть.
        """
        url = response.request.url
        match = re.search(r"/lots/view/(\d+)", url)
        if match is None:
            # Без идентификатора документ нечем ключевать в хранилище.
            await self.log(f"пропуск: в ссылке нет номера лота — {url}")
            return

        row, page = response.metadata["row"], response.selector()
        lot = Lot.model_validate(
            {
                "source": self.name,
                "lot_id": match.group(1),
                "url": url,
                "fetched_at": datetime.now(UTC).isoformat(),
                "trade_id": row["trade_id"],
                "trade_number": row["trade_id"],
                "lot_num": row["lot_num"],
                "trade_type": row["trade_type"],
                # Вторая колонка листинга: в coll-temp она звалась debtor,
                # хотя там название торгов («Продажа имущества …»).
                "debtor": row["auction_name"],
                "organizer": row["organizer"],
                "winner": row["winner"],
                "description": row["description"],
                "lot_url": row["lot_url"],
                "price": parse_price(row["price"]),
                "price_raw": row["price"],
                "status": row["status"],
                "bidding_date": row["bids_end"],
                "event_date": row["auction_date"],
                "detail": parse_detail(page),
                "attachments": parse_attachments(page),
                "price_schedule": parse_price_schedule(page),
            }
        )
        yield lot.model_dump()


def narrow(**overrides: Any) -> Settings:
    """Настройки площадки: общие плюс её особенность.

    Через ``replace``, а не конструктором, чтобы площадка со своей причудой
    не теряла общие ``delay`` и ``timeout``, когда те поменяются.
    """
    return replace(BASE_SETTINGS, **overrides)


# ── запуск одной площадки ────────────────────────────────────────────────────


async def crawl(parser_cls: type[TenderFogsoft]) -> tuple[Any, int, int, int, str]:
    """Обойти площадку, складывая лоты в хранилище по мере поступления.

    Поток, а не ``collect()``: айтемы пишутся сразу, и обход, прерванный на
    середине, оставляет после себя всё, что успел собрать.
    """
    new = updated = 0
    async with MongoStore(parser_cls.name) as store:
        async with open_crawler(parser_cls) as crawler:
            async for item in crawler.stream():
                if await store.upsert(item):
                    new += 1
                else:
                    updated += 1
        return crawler.stats, new, updated, await store.count(), store.target


def main(parser_cls: type[TenderFogsoft]) -> None:
    """Точка входа модуля площадки: ``python -m tp.centerr``."""
    # Логи парсера и фреймворка идут через stdlib logging уровнем INFO, а у root
    # по умолчанию нет обработчиков и порог WARNING — без basicConfig всё INFO
    # молча отбрасывается. Консоль Windows вдобавок не UTF-8, а в логах кириллица.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    stats, new, updated, total, target = asyncio.run(crawl(parser_cls))

    print(f"лотов получено {stats.items}: новых {new}, обновлено {updated}")
    print(f"запросов {stats.requests}, ошибок {stats.errors}, причина остановки {stats.reason}")
    print(f"в хранилище {total} документов -> {target}")
