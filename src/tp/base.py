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
с записями ``длина|тип|имя|значение|``), и форма на каждом шаге та же, что на
первом. Тело POST собирает ``Response.form_request()`` фреймворка — все поля
формы, как отправил бы браузер, с токенами ``__CVIEWSTATE`` и
``__EVENTVALIDATION`` в их числе; парсер называет только то, что меняет.

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
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from typing import Any, ClassVar

from collector import Crawler, Response, Settings, open_crawl
from parsel import Selector
from pydantic import ValidationError

from core.db import MongoStore
from core.labels import canon_detail
from core.lot import Lot
from core.parsing import parse_datetime, parse_price
from core.settings import settings as config

#: Настройки HTTP, общие для всех площадок движка. Площадка со своей
#: особенностью narrows их через ``replace`` — см. arbbitlot и meta_invest.
#:
#: concurrency остаётся единицей, и это измерено, а не осторожность: площадка
#: обрабатывает наши запросы по одному, поэтому латентность растёт ровно
#: пропорционально числу воркеров, а запросов в секунду не прибавляется.
#:
#: max_errors — сколько упавших запросов площадка переживает. Фреймворк по
#: умолчанию останавливает обход на первом, и одна битая страница лота роняла
#: бы площадку на тысяче лотов. Разбор лота сам почти не падает (невалидный
#: лот пишется запасным документом), так что ошибка здесь — это сеть после
#: ретраев или вёрстка, сломанная для всех страниц. 50 — около 2,5% от
#: 2000 запросов обхода в 100 страниц: случайные сбои проходят, а сломанная
#: вёрстка останавливает площадку через 50 впустую потраченных запросов, а не
#: через две тысячи. На один прогон — ``--max-errors``.
BASE_SETTINGS = Settings(concurrency=1, delay=config.delay, timeout=config.http_timeout, max_errors=50)


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


#: Поля формы поиска над листингом: у всех площадок движка они внутри
#: раскрывающейся панели, и её id входит в имя каждого поля.
SEARCH_PANEL = "phExpandCollapse"


def filter_resets(page: Selector) -> dict[str, str]:
    """Выпадающие списки формы поиска, где выбрано не «Все», -> значение «Все».

    Площадка может открывать листинг с фильтром по умолчанию: centerr
    показывает только «Прием заявок», и без сброса в базу не попадает ни один
    завершённый лот. Сбрасываем не только статус, а любой список с вариантом
    «Все», — какой фильтр выставит следующая площадка, заранее не знать.
    Список без «Все» — не фильтр, его не трогаем. Пустой словарь — сбрасывать
    нечего.
    """
    resets: dict[str, str] = {}
    for select in page.xpath(f"//select[contains(@name, '{SEARCH_PANEL}')]"):
        first = select.xpath("./option[1]")
        if clean(first.xpath("string(.)").get()) != "Все":
            continue
        everything = first.attrib.get("value", "")
        chosen = select.xpath("./option[@selected]/@value").get()
        if chosen is not None and chosen != everything:
            resets[select.attrib["name"]] = everything
    return resets


def search_button(page: Selector) -> str | None:
    """Имя кнопки поиска. Она стоит в панели первой, перед «Очистить»."""
    return page.xpath(f"//input[@type='submit'][contains(@name, '{SEARCH_PANEL}')][1]/@name").get()


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
    """Разделы страницы лота, сведённые к одному написанию (см. ``core.labels``).

    Отказы от договора здесь отброшены — их отдаёт ``canon_detail`` вторым
    значением, и ``parse_lot`` берёт оба сразу.
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


@dataclass(frozen=True)
class FogsoftParams:
    """Что задаётся на один прогон: предел страниц и окно по дате.

    Раньше это были атрибуты класса, и run_all переписывал их у класса на весь
    процесс: два обхода в одном процессе видели значения друг друга. Теперь
    фреймворк собирает свой экземпляр на каждый прогон, приводит строки из
    командной строки к типам и отказывает в незнакомом ключе до первого
    запроса — окно, молча не применённое из-за опечатки, обошло бы всё.

    Умолчания — из ``core.settings``, то есть из окружения.
    """

    #: Предохранитель обхода. Без потолка ошибка в пагинации крутится вечно.
    max_pages: int = config.max_pages
    #: Окно по дате, см. ``Settings.since`` и ``page_is_older``.
    since: date | None = config.since


# ── парсер ───────────────────────────────────────────────────────────────────


class TenderFogsoft(Crawler):
    """Наследнику достаточно задать ``name`` и ``DOMAIN``."""

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "public/purchases-all/"

    settings = BASE_SETTINGS
    params = FogsoftParams()

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
            resets, button = filter_resets(page), search_button(page)
            if resets and button:
                # Строки этой страницы отфильтрованы — их не берём: та же первая
                # страница придёт заново уже без фильтра. Кнопка называется
                # явно: в форме WebForms вся страница, и первая кнопка в ней —
                # «Войти», а не «Искать».
                await self.log("листинг открылся с фильтром — сбрасываю")
                yield response.form_request(
                    formdata=resets, click=button, metadata={"page": 1, "filters_reset": True}
                )
                return
            if resets:
                await self.log("листинг открылся с фильтром, а кнопки поиска нет — иду как есть")

        rows = parse_rows(page)
        await self.log(f"{response.status} | страница {num_page} | лотов {len(rows)}")

        for row in rows:
            if row["lot_url"]:
                yield response.follow(row["lot_url"], callback=self.parse_lot, metadata={"row": row})

        if num_page >= self.params.max_pages:
            await self.log(f"остановка: предел max_pages={self.params.max_pages}")
            return

        since = self.params.since
        if since is not None and page_is_older(rows, since):
            await self.log(f"остановка: вся страница {num_page} закрыла приём заявок до {since}")
            return

        next_target = find_next_target(page, num_page)
        if next_target is None:
            await self.log(f"страница {num_page} последняя")
            return

        if not page.xpath("//input[@name='__CVIEWSTATE']/@value").get():
            # Пост без токенов сервер ответит первой страницей, и обход пошёл бы
            # по кругу. Молча выйти здесь — выдать обрыв цепочки за её конец.
            await self.log(f"страница {num_page}: токенов нет, дальше идти нечем")
            return

        # Клик по ссылке пейджера: __doPostBack кладёт её цель в __EVENTTARGET,
        # остальное — поля формы как есть.
        yield response.form_request(
            formdata={"__EVENTTARGET": next_target, "__EVENTARGUMENT": ""},
            metadata={"page": num_page + 1},
        )

    async def parse_lot(self, response: Response) -> Any:
        """Страница лота: слить строку листинга с подробностями в один айтем."""
        url = response.request.url
        match = re.search(r"/lots/view/(\d+)", url)
        if match is None:
            # Без идентификатора документ нечем ключевать в хранилище.
            await self.log(f"пропуск: в ссылке нет номера лота — {url}")
            return

        item = build_item(self.name, match.group(1), url, response.metadata["row"], response.selector())
        if not item["validation"]["ok"] and "row" in item:
            await self.log(f"лот {match.group(1)} не прошёл модель: {item['validation']['errors'][0][:120]}")
        yield item


def build_item(source: str, lot_id: str, url: str, row: dict[str, Any], page: Selector) -> dict[str, Any]:
    """Айтем лота: строка листинга и страница лота через модель ``core.lot.Lot``.

    Модель типизирует цену и сроки листинга, сводит разделы страницы в
    ``extra`` и пишет итог сверок в ``validation``. Если модель лот всё же не
    пропустила, он не теряется: без запасного документа исключение ушло бы в
    collector, тот посчитал бы ошибку, и лот не попал бы в базу вовсе — из-за
    одного поля. Запасной документ несёт ключ, сырую строку листинга и текст
    ошибки в ``validation``, чтобы разбирать его было из чего.
    """
    fetched_at = datetime.now(UTC).isoformat()
    extra, refusals = canon_detail(raw_detail(page))
    try:
        lot = Lot.model_validate(
            {
                "source": source,
                "lot_id": lot_id,
                "url": url,
                "fetched_at": fetched_at,
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
                "detail": extra,
                "refusals": refusals,
                "attachments": parse_attachments(page),
                "price_schedule": parse_price_schedule(page),
            }
        )
    except ValidationError as exc:
        return {
            "source": source,
            "lot_id": lot_id,
            "url": url,
            "fetched_at": fetched_at,
            "row": row,
            "validation": {"ok": False, "errors": [f"модель: {exc}"], "unknown_labels": []},
        }
    return lot.model_dump()


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
        async with open_crawl(parser_cls) as crawl:
            async for item in crawl.stream():
                if await store.upsert(item):
                    new += 1
                else:
                    updated += 1
        return crawl.stats, new, updated, await store.count(), store.target


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
