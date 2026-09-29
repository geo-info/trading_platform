# Перенос kendo, btorg, rus-on на схему iTender — план реализации

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Движки kendo, btorg, rus-on из `src/tp/delete/` переписаны пакетами `tp/<движок>/{base,detail,source}.py` по образцу `tp/itender/`; лот листинга — общая модель `core.lot.Lot`.

**Architecture:** base обходит листинг подряд (без фильтра статуса) до `max_pages`, заходит на страницу торгов и отдаёт `Lot(...).model_dump()` на каждый лот. detail — примесь к классу площадки (`detail_of`), берёт лоты из `ctx.sink.pending_detail`, запрашивает страницу торгов один раз на торги и отдаёт `{"lot_id", "detail"}`. Разбор — чистые функции модуля, перенесённые из `delete/`.

**Tech Stack:** Python 3.11+, collector-framework (`Crawler`, `Response`, `Settings`), parsel, pydantic 2, MongoDB (pymongo async).

**Спека:** `docs/superpowers/specs/2026-09-29-engines-refactor-design.md`

**Ограничения:** `src/tp/itender/` и `src/tp/delete/` не менять. Тестов в репозиторий не добавлять (решение пользователя: тесты — отдельным этапом). Проверка — `ruff`, скрипт-разбор фикстур и живой прогон из scratchpad. Стиль кода — как в `tp/itender/`: докстринги по-русски, `from __future__ import annotations`, чистые функции разбора над классом краулера.

**Команды** выполняются из корня репозитория `P:\hub\geo-info\trading_platform`. Scratchpad: `C:\Users\killler\AppData\Local\Temp\claude\P--hub-geo-info-trading-platform\0c286b0a-177f-4414-9af9-82b75f390072\scratchpad` (ниже — `$SCRATCH`).

---

## Файлы

| Файл | Что | Задача |
|---|---|---|
| `src/core/help.py` | + `MSK`, `digits`, `parse_price`, `parse_datetime` | 1 |
| `src/core/lot.py` | новый: `Lot`, `is_active_status` | 2 |
| `src/core/db/mongo/storage.py` | `pending_detail` отдаёт `trade_url` | 3 |
| `src/tp/kendo/{__init__,base,detail,source}.py` | движок Kendo-ETP, 5 площадок | 4 |
| `src/tp/btorg/{__init__,base,detail,source}.py` | движок btorg, 6 площадок | 5 |
| `src/tp/ruson/{__init__,base,detail,source}.py` | движок rus-on, 5 площадок | 6 |
| — | живой прогон по площадке каждого движка | 7 |

---

### Task 1: Помощники разбора в `core/help.py`

**Files:**
- Modify: `src/core/help.py` (весь файл)

- [ ] **Step 1: Заменить содержимое `src/core/help.py`**

```python
"""Мелкие помощники разбора, общие для парсеров.

Разбор значений (цена, дата) при неудаче молча возвращает ``None``: лот не
должен падать из-за одной кривой ячейки, сырая строка всё равно остаётся в
документе.
"""

from __future__ import annotations

import re
from datetime import datetime
from itertools import takewhile
from zoneinfo import ZoneInfo

#: Часовой пояс площадок. На Windows база поясов приходит пакетом tzdata.
MSK = ZoneInfo("Europe/Moscow")

#: Ведущая числовая часть: пробелы как разделители тысяч, точка или запятая
#: как десятичная. Останавливается перед хвостом «руб, НДС не облагается».
_PRICE_HEAD_RE = re.compile(r"[\d\s.,]+")
#: ДД.ММ.ГГГГ с необязательным ЧЧ:ММ[:СС]; хвост вроде «(33 дн.)» не мешает.
_DATETIME_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\D+(\d{2}):(\d{2})(?::(\d{2}))?)?")


def clean(value: str | None) -> str | None:
    """Схлопнуть пробелы и неразрывные пробелы; пустая строка — это ``None``."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip() or None


def digits(text: str | None) -> str:
    """Ведущие цифры строки: «10840–ОАОФ» -> «10840»."""
    return "".join(takewhile(str.isdigit, text or ""))


def parse_price(value: str | None) -> float | None:
    """Сумма в рублях: «270 000,00», «1 315 000.00», «280 000,00 руб, НДС…»."""
    m = _PRICE_HEAD_RE.match(clean(value) or "")
    if not m:
        return None
    raw = m.group(0).replace(" ", "").replace(",", ".").rstrip(".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_datetime(value: str | None) -> datetime | None:
    """«ДД.ММ.ГГГГ[ ЧЧ:ММ[:СС]]» -> datetime по Москве, иначе ``None``.

    Площадки пишут московское время, не говоря об этом. Наивный datetime
    драйвер Mongo сохранил бы как UTC, и торги сдвинулись бы на три часа.
    """
    m = _DATETIME_RE.search(value or "")
    if not m:
        return None
    day, month, year, hour, minute, second = m.groups()
    try:
        return datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0), tzinfo=MSK
        )
    except ValueError:
        return None
```

- [ ] **Step 2: Проверить руками**

Run:
```bash
uv run python -c "from core.help import parse_price as p, parse_datetime as d; print(p('1 234 567,89'), p('280 000,00 руб, НДС'), p('Купить с агентом'), d('28.10.2026 10:00 (34 дн.)'), d('10.09.2026'), d('когда-нибудь'))"
```
(с `PYTHONPATH=src`, если пакет не установлен в editable-режиме: `PYTHONPATH=src uv run python -c ...`)

Expected: `1234567.89 280000.0 None 2026-10-28 10:00:00+03:00 2026-09-10 00:00:00+03:00 None`

- [ ] **Step 3: Commit**

```bash
git add src/core/help.py
git commit -m "core.help: digits, parse_price, parse_datetime по Москве"
```

---

### Task 2: Модель `core/lot.py`

**Files:**
- Create: `src/core/lot.py`

- [ ] **Step 1: Создать `src/core/lot.py`**

```python
"""Lot — лот листинга, один на все движки и площадки.

Поля названы так, как их отдаёт строка листинга iTender, — у остальных движков
то же самое называется так же. Значения — как на площадке, строками: так
документ можно сверить со страницей глазами. Рядом — разобранные значения
(``price_value``, ``bids_end_at``, ``auction_at``, ``is_active``): их модель
считает сама, в документ они попадают через ``model_dump()``.

Детали лота — не здесь: их дописывает детальный парсер отдельным полем
``detail`` (``Store.save_detail``), у каждого движка своего вида. Модель
описывает то, что кладёт в базу листинг.

Незнакомые поля запрещены: опечатка в имени поля у парсера всплывает сразу, а
не копится в базе вторым написанием того же.

    item = Lot(source="bep", lot_id="1", lot_url="https://…", price="135 000.00").model_dump()
    await storage.upsert(item)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from core.help import parse_datetime, parse_price

#: Части статусов, означающих, что торги закончены. Всё остальное, включая
#: незнакомый или пустой статус, считается живым: лот не теряется на сомнении.
FINISHED_MARKERS = (
    "заверш",
    "состоял",
    "отмен",
    "приостановлен",
    "аннулирован",
    "признан",
    "окончен",
)


def is_active_status(status: str | None) -> bool:
    """Идут ли ещё торги. Незнакомый или пустой статус — идут."""
    lowered = (status or "").lower().replace("ё", "е")
    return not any(marker in lowered for marker in FINISHED_MARKERS)


class Lot(BaseModel):
    """Один лот торгов, как его видит листинг."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Площадка — ``name`` краулера; вместе с ``lot_id`` — ключ документа.
    source: str
    #: Номер лота, уникальный внутри площадки.
    lot_id: str
    #: Страница лота для человека. Если своей страницы у лота нет — страница торгов.
    lot_url: str
    #: Откуда детальный парсер берёт детали: страница торгов или фрагмент с
    #: лотами. Лоты одних торгов делят один адрес.
    trade_url: str | None = None

    trade_id: str | None = None
    #: Номер торгов, как его пишет площадка: «10840–ОАОФ».
    trade_number: str | None = None
    trade_type: str | None = None
    auction_name: str | None = None
    lot_num: str | None = None
    description: str | None = None

    organizer: str | None = None
    debtor: str | None = None
    winner: str | None = None

    #: Начальная цена, как на площадке.
    price: str | None = None
    #: Окончание приёма заявок, как на площадке.
    bids_end: str | None = None
    #: Дата торгов (подведения результатов), как на площадке.
    auction_date: str | None = None
    status: str | None = None

    @computed_field
    @property
    def price_value(self) -> float | None:
        return parse_price(self.price)

    @computed_field
    @property
    def bids_end_at(self) -> datetime | None:
        return parse_datetime(self.bids_end)

    @computed_field
    @property
    def auction_at(self) -> datetime | None:
        return parse_datetime(self.auction_date)

    @computed_field
    @property
    def is_active(self) -> bool:
        return is_active_status(self.status)
```

- [ ] **Step 2: Проверить руками**

Run:
```bash
PYTHONPATH=src uv run python -c "from core.lot import Lot; print(Lot(source='x', lot_id='1_1', lot_url='u', price='1 000,50', bids_end='01.10.2026 12:00', status='Торги завершены').model_dump())"
```
Expected: словарь с `price_value: 1000.5`, `bids_end_at: datetime(2026, 10, 1, 12, 0, tzinfo=...Moscow)`, `is_active: False`.

Run:
```bash
PYTHONPATH=src uv run python -c "from core.lot import Lot; Lot(source='x', lot_id='1', lot_url='u', typo='y')"
```
Expected: `pydantic_core._pydantic_core.ValidationError ... Extra inputs are not permitted`.

- [ ] **Step 3: Commit**

```bash
git add src/core/lot.py
git commit -m "core.lot: общая модель лота листинга"
```

---

### Task 3: `pending_detail` отдаёт `trade_url`

**Files:**
- Modify: `src/core/db/mongo/storage.py` — метод `MongoStorage.pending_detail`

- [ ] **Step 1: Поправить проекцию и докстринг**

В `pending_detail` заменить

```python
        projection = {"_id": 0, "lot_id": 1, "lot_url": 1}
```

на

```python
        # trade_url — адрес страницы торгов: у kendo, btorg и rus-on детали
        # берутся с неё. У лотов iTender поля нет — в выдаче его просто не будет.
        projection = {"_id": 0, "lot_id": 1, "lot_url": 1, "trade_url": 1}
```

В `src/core/db/base.py` в докстринге `Store.pending_detail` заменить
`"""``lot_id`` и ``lot_url`` лотов, …` на
`"""``lot_id``, ``lot_url`` и (если есть) ``trade_url`` лотов, …` — остальной текст оставить.

- [ ] **Step 2: Проверить**

Run: `uv run ruff check src/core`
Expected: `All checks passed!`

- [ ] **Step 3: Commit**

```bash
git add src/core/db/mongo/storage.py src/core/db/base.py
git commit -m "pending_detail: отдавать trade_url для деталей со страницы торгов"
```

---

### Task 4: Движок kendo

**Files:**
- Create: `src/tp/kendo/__init__.py` (пустой)
- Create: `src/tp/kendo/base.py`
- Create: `src/tp/kendo/detail.py`
- Create: `src/tp/kendo/source.py`
- Справочник: `src/tp/delete/kendo.py`, `src/tp/delete/kendo_platforms.py`
- Фикстуры для проверки: `tests/kendo/fixtures/listing_trade_alliance.html`, `tests/kendo/fixtures/trade_10840.html`

- [ ] **Step 1: Создать пустой `src/tp/kendo/__init__.py`**

- [ ] **Step 2: Создать `src/tp/kendo/base.py`**

```python
"""Базовый парсер движка Kendo-ETP.

Листинг ``/lots`` — карточки ``block-lot``: на одних площадках карточка на
торги (``<a>``), на других — на лот (``<div>``). В обоих вариантах есть ссылка
«Номер торгов» ``/{тип}/{id}`` — адрес торгов. Лоты и цены — только на
странице торгов: ``div#lots``; организатор и сроки — пары ``div.table_row`` в
``div#main-info``. Повторный заход в одни торги отсекает дедупликация
запросов фреймворка.

Площадка наследует ``Kendo`` и задаёт ``name`` и ``DOMAIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits
from core.lot import Lot


def is_trade_number(text: str) -> bool:
    """«10775–ОАОФ» / «37-ОАОФ»: цифры, затем тире или дефис.

    Так номер торгов отличается от названия среди жирных строк карточки.
    """
    head = digits(text)
    return bool(head) and text[len(head) :].lstrip()[:1] in ("–", "-")


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Страница листинга -> торги, без повторов внутри страницы."""
    trades: list[dict[str, Any]] = []
    seen: set[str] = set()
    for card in page.xpath('//*[contains(@class, "block-lot")]'):
        number = number_href = title = None
        for bold in card.xpath('.//*[contains(@class, "bold")]'):
            text = clean(bold.xpath("string(.)").get())
            if not text:
                continue
            if is_trade_number(text):
                number, number_href = text, bold.xpath(".//a/@href").get()
            elif title is None:
                title = text
        # Адрес торгов: сама карточка-ссылка или ссылка номера в карточке лота.
        trade_url = card.xpath("./@href").get() or number_href
        trade_id = digits(number)
        if not trade_id or not trade_url or trade_id in seen:
            continue
        seen.add(trade_id)
        parts = number.split("–")
        trades.append(
            {
                "trade_id": trade_id,
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "trade_title": title,
                "trade_url": trade_url,
                "bids_end": clean(card.xpath('.//nobr[i[@title="Окончание приема заявок"]]/text()').get()),
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> tuple[int, str] | None:
    """Номер и ссылка ближайшей следующей страницы пейджера; ``None`` — страница последняя.

    Берётся ссылка самого пейджера, а не собранный адрес: в ней уже все
    параметры листинга, которые площадка сочла нужными.
    """
    later = []
    for href in page.xpath('//ul[contains(@class, "pagination")]//a[contains(@href, "page=")]/@href').getall():
        n = digits(href.split("page=", 1)[1])
        if n and int(n) > num_page:
            later.append((int(n), href))
    return min(later) if later else None


def parse_main_info(page: Selector) -> dict[str, str]:
    """Пары «подпись: значение» из ``#main-info``; повторная подпись — выигрывает последняя."""
    info: dict[str, str] = {}
    for row in page.xpath('//div[@id="main-info"]//div[contains(@class, "table_row")]'):
        label = clean(row.xpath('string(./div[contains(@class, "grey-text")][1])').get())
        value = clean(row.xpath('string(./div[contains(@class, "l9")][1])').get())
        if label and value:
            info[label.rstrip(":").strip()] = value
    return info


def debtor_of(title: str | None) -> str | None:
    """Должник — хвост заголовка карточки «…, должник X» (или «должника X»)."""
    at = (title or "").lower().rfind("должник")
    parts = (title or "")[at:].split(maxsplit=1) if at >= 0 else []
    return parts[1].strip() if len(parts) == 2 else None


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Лоты из ``div#lots`` -> поля ``Lot`` без ``source`` и адресов.

    ``lot_href`` — ссылка на страницу лота как в разметке; сроки и организатор —
    со страницы торгов, срок из карточки листинга — запасной.
    """
    main = parse_main_info(page)
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "debtor": debtor_of(trade.get("trade_title")),
        "organizer": main.get("Наименование"),
        "bids_end": main.get("Окончание приема заявок") or trade.get("bids_end"),
        "auction_date": main.get("Подведение результатов торгов"),
    }
    lots = []
    for block in page.xpath('//div[@id="lots"]//*[contains(@class, "block-lot")]'):
        link = block.xpath('.//a[contains(@href, "/lots/")][1]')
        lot_num = clean(block.xpath('.//span[contains(@class, "black-text")]/text()').get())
        if not lot_num:
            continue
        lots.append(
            {
                **shared,
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "lot_num": lot_num,
                "lot_href": link.xpath("./@href").get(),
                "description": clean(link.xpath("string(.)").get()),
                "price": clean(block.xpath('string(.//span[contains(@class, "fs36")])').get()),
                "status": clean(
                    block.xpath('.//span[contains(@class, "lot-status")]/following-sibling::text()').get()
                ),
            }
        )
    return lots


@dataclass(frozen=True)
class KendoParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class Kendo(Crawler):

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "lots"

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50,
    )
    params = KendoParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга — из домена площадки.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Страница листинга: зайти в каждые торги, затем следующая страница."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        trades = parse_listing(page)
        await self.log(f"страница {num_page}: торгов {len(trades)}")

        for trade in trades:
            yield response.follow(trade["trade_url"], callback = self.parse_trade, metadata = {"trade": trade})

        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            number, href = next_page
            yield response.follow(href, metadata = {"num_page": number})

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по ``Lot`` на лот."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        trade_url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            href = lot.pop("lot_href")
            yield Lot(
                source = self.name,
                lot_url = response.urljoin(href) if href else trade_url,
                trade_url = trade_url,
                **lot,
            ).model_dump()
```

- [ ] **Step 3: Создать `src/tp/kendo/detail.py`**

```python
"""Детальный парсер Kendo-ETP: страница торгов -> сведения о торгах и документы.

Какие лоты обходить, решает база (``MongoStorage.pending_detail``). Детали у
Kendo — на странице торгов, общие для всех её лотов: пары ``#main-info`` и
документы ``#documents``. Страница запрашивается один раз на торги, детали
получает каждый ожидающий лот этих торгов.

Как и у iTender, детальный парсер — примесь к классу площадки: ``detail_of(Seltim)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from core.help import clean
from tp.kendo.base import Kendo, parse_main_info


def parse_documents(page: Selector) -> list[dict[str, Any]]:
    """Документы торгов: имя и ссылка из ``#documents``."""
    documents = []
    for row in page.xpath('//div[@id="documents"]//div[contains(@class, "file-row")]'):
        link = row.xpath('.//a[starts-with(@href, "http")][1]')
        if url := link.xpath("./@href").get():
            documents.append({"name": clean(link.xpath("string(.)").get()), "url": url})
    return documents


def parse_detail(page: Selector) -> dict[str, Any]:
    """Детали торгов: пары «подпись: значение» и ``attachments``."""
    return {**parse_main_info(page), "attachments": parse_documents(page)}


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class KendoDetail(Kendo):
    """Примесь: вместо листинга — страницы торгов лотов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            yield self.request(url, metadata = {"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        detail = parse_detail(response.selector())
        for lot_id in response.metadata["lot_ids"]:
            yield {"lot_id": lot_id, "detail": detail}


def detail_of(platform: type[Kendo]) -> type[KendoDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы торгов."""
    return type(f"{platform.__name__} Detail", (KendoDetail, platform), {"__module__": platform.__module__})
```

- [ ] **Step 4: Создать `src/tp/kendo/source.py`**

```python
"""Площадки на движке Kendo-ETP."""

from __future__ import annotations

from tp.kendo.base import Kendo


class TradeAlliance(Kendo):
    """Альянс Трэйд."""

    name = "trade_alliance"
    DOMAIN = "https://trade-alliance.ru"


class Seltim(Kendo):
    """Селтим."""

    name = "seltim"
    DOMAIN = "https://bankrupt.seltim.ru"


class ElectroTorgi(Kendo):
    """Электро-Торги."""

    name = "electro_torgi"
    DOMAIN = "https://bankrotstvo.electro-torgi.ru"


class Torgi82(Kendo):
    """Торги82."""

    name = "torgi82"
    DOMAIN = "https://lot.torgi82.ru"


class Vetp(Kendo):
    """ВЭТП. Домен кириллический — в punycode его переводит curl."""

    name = "vetp"
    DOMAIN = "https://банкрот.вэтп.рф"


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Kendo]] = {
    cls.name: cls for cls in Kendo.__subclasses__() if cls.__module__ == __name__
}
```

- [ ] **Step 5: Проверить разбор на фикстурах**

Создать `$SCRATCH/check_kendo.py`:

```python
from pathlib import Path

from parsel import Selector

from core.lot import Lot
from tp.kendo.base import find_next_page, parse_listing, parse_lots
from tp.kendo.detail import parse_detail
from tp.kendo.source import PLATFORMS

FIX = Path("tests/kendo/fixtures")
listing = Selector((FIX / "listing_trade_alliance.html").read_text(encoding="utf-8"))
trades = parse_listing(listing)
print("торгов", len(trades), trades[0])
print("следующая", find_next_page(listing, 1))

trade_page = Selector((FIX / "trade_10840.html").read_text(encoding="utf-8"))
trade = next((t for t in trades if t["trade_id"] == "10840"), {"trade_id": "10840"})
lots = parse_lots(trade_page, trade)
print("лотов", len(lots))
for lot in lots:
    href = lot.pop("lot_href")
    print(Lot(source="trade_alliance", lot_url=href or "x", trade_url="x", **lot).model_dump())
detail = parse_detail(trade_page)
print("деталей", len(detail) - 1, "документов", len(detail["attachments"]))
print("площадки", sorted(PLATFORMS))
```

Run: `PYTHONPATH=src uv run python $SCRATCH/check_kendo.py`

Expected: `торгов` > 0; `следующая (2, '...page=2...')`; `лотов` ≥ 1, у лотов заполнены `lot_num`, `price`, `price_value` (число), `status`, `organizer`; `деталей` > 0; `площадки ['electro_torgi', 'seltim', 'torgi82', 'trade_alliance', 'vetp']`. Если какое-то поле пусто, а в `delete/kendo.py` на той же фикстуре оно было, — ошибка переноса, сверить функцию построчно.

- [ ] **Step 6: ruff**

Run: `uv run ruff check src/tp/kendo`
Expected: `All checks passed!` (при замечаниях isort — `uv run ruff check --fix src/tp/kendo`).

- [ ] **Step 7: Commit**

```bash
git add src/tp/kendo
git commit -m "Kendo-ETP по образцу iTender: base, detail, source"
```

---

### Task 5: Движок btorg

**Files:**
- Create: `src/tp/btorg/__init__.py` (пустой)
- Create: `src/tp/btorg/base.py`
- Create: `src/tp/btorg/detail.py`
- Create: `src/tp/btorg/source.py`
- Справочник: `src/tp/delete/btorg.py`, `src/tp/delete/btorg_platforms.py`
- Фикстуры: `tests/btorg/fixtures/listing_atctrade.html`, `tests/btorg/fixtures/lots_13147.html`

- [ ] **Step 1: Создать пустой `src/tp/btorg/__init__.py`**

- [ ] **Step 2: Создать `src/tp/btorg/base.py`**

```python
"""Базовый парсер движка btorg (edoc-ETP).

Листинг ``/etp/trade/list.html`` — ``table.data``, строка на торги; цен в нём
нет, поэтому в каждые торги заходим за AJAX-фрагментом лотов
``inner-view-lots.html`` (с признаком XHR). Во фрагменте — по ``table.data``
на лот (``id="lotNumberN"``) с парами «подпись — значение» и, у публичного
предложения, вложенной таблицей интервалов снижения цены. Своей страницы у
лота нет: его адрес — адрес фрагмента. Страницы — в windows-1251,
перекодирует их фреймворк по заголовку ответа.

Площадка наследует ``Btorg`` и задаёт ``name`` и ``DOMAIN``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits
from core.lot import Lot

#: AJAX-фрагмент с лотами торгов — с ценами, которых нет в листинге.
LOTS_PATH = "/etp/trade/inner-view-lots.html"
#: Фрагмент лотов отдаётся только на AJAX-запрос.
XHR = {"X-Requested-With": "XMLHttpRequest"}


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Строки ``table.data`` -> торги.

    Внутренний id торгов, по которому запрашиваются лоты, — в ``onclick``
    строки (``…general.html?id=NNN…``). Колонка «Организатор» идёт перед
    «Должником».
    """
    trades = []
    for row in page.xpath('//table[@class="data"]//tr[@onclick]'):
        purchase = digits(row.xpath('substring-after(@onclick, "id=")').get())
        cells = row.xpath("./td")
        number = clean(cells[0].xpath("string(.)").get()) if cells else None
        if not purchase or len(cells) < 5 or not digits(number):
            continue
        parts = number.split("-")
        trades.append(
            {
                "trade_id": digits(number),
                "trade_number": number,
                "trade_type": clean(parts[1]) if len(parts) == 2 else None,
                "organizer": clean(cells[1].xpath("string(.)").get()),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(cells[2].xpath('.//div[contains(@style, "bold")]//text()').get()),
                "status": clean(cells[3].xpath("string(.)").get()),
                "trade_url": f"{LOTS_PATH}?perspective=inline&id={purchase}",
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> tuple[int, str] | None:
    """Номер и ссылка ближайшей следующей страницы пейджера; ``None`` — страница последняя."""
    later = []
    for href in page.xpath('//a[contains(@href, "list.html?page=")]/@href').getall():
        n = digits(href.split("page=", 1)[1])
        if n and int(n) > num_page:
            later.append((int(n), href))
    return min(later) if later else None


def lot_tables(page: Selector) -> list[tuple[str, Selector]]:
    """Таблицы лотов фрагмента: номер лота и таблица ``lotNumberN``."""
    tables = []
    for table in page.xpath('//table[contains(@id, "lotNumber")]'):
        if lot_num := table.xpath('substring-after(@id, "lotNumber")').get():
            tables.append((lot_num, table))
    return tables


def lot_pairs(lot: Selector) -> dict[str, str]:
    """Пары «подпись: значение» таблицы лота.

    Только свои строки таблицы лота — строки вложенной таблицы интервалов
    дали бы подписи-даты.
    """
    rows = lot.xpath(".//tr[td[2]][ancestor::table[1][contains(@id, 'lotNumber')]]")
    return {
        label.rstrip(":").strip(): value
        for row in rows
        if (label := clean(row.xpath("string(./td[1])").get()))
        and (value := clean(row.xpath("string(./td[2])").get()))
    }


def parse_schedule(lot: Selector) -> list[dict[str, str]]:
    """Интервалы снижения цены публичного предложения: строка -> {заголовок: ячейка}."""
    table = lot.xpath('.//table[contains(@class, "inner")]')
    headers = [clean(td.xpath("string(.)").get()) or "" for td in table.xpath(".//tr[1]/*")]
    schedule = []
    for row in table.xpath(".//tr[position() > 1]"):
        cells = [clean(td.xpath("string(.)").get()) or "" for td in row.xpath("./td")]
        if headers and len(cells) == len(headers):
            schedule.append(dict(zip(headers, cells, strict=True)))
    return schedule


def property_details(pairs: dict[str, str]) -> str | None:
    """«Сведения об имуществе должника…» — описание, где «Предмет торгов» не заполнен.

    Ищется по вхождению: первая «С» в подписи на части площадок латинская.
    """
    return next((value for label, value in pairs.items() if "ведения об имуществе" in label), None)


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Таблицы ``lotNumberN`` фрагмента -> поля ``Lot`` без ``source`` и адресов."""
    lots = []
    for lot_num, table in lot_tables(page):
        pairs = lot_pairs(table)
        schedule = parse_schedule(table)
        lots.append(
            {
                "lot_id": f"{trade['trade_id']}_{lot_num}",
                "trade_id": trade["trade_id"],
                "trade_number": trade.get("trade_number"),
                "trade_type": trade.get("trade_type"),
                "lot_num": lot_num,
                "debtor": trade.get("debtor"),
                "organizer": trade.get("organizer"),
                "description": pairs.get("Предмет торгов") or property_details(pairs),
                "price": pairs.get("Начальная цена продажи имущества"),
                "status": pairs.get("Статус торгов") or trade.get("status"),
                # Срок приёма публичного предложения — конец последнего интервала.
                "bids_end": schedule[-1].get("Дата окончания приема заявок") if schedule else None,
            }
        )
    return lots


@dataclass(frozen=True)
class BtorgParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class Btorg(Crawler):

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "etp/trade/list.html"

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50,
    )
    params = BtorgParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга — из домена площадки.
        if "DOMAIN" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Страница листинга: зайти за лотами каждых торгов, затем следующая страница."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        trades = parse_listing(page)
        await self.log(f"страница {num_page}: торгов {len(trades)}")

        for trade in trades:
            yield response.follow(
                trade["trade_url"], callback = self.parse_trade, headers = XHR, metadata = {"trade": trade}
            )

        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            number, href = next_page
            yield response.follow(href, metadata = {"num_page": number})

    async def parse_trade(self, response: Response) -> Any:
        """Фрагмент лотов торгов: по ``Lot`` на лот; адрес лота — адрес фрагмента."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        trade_url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            yield Lot(source = self.name, lot_url = trade_url, trade_url = trade_url, **lot).model_dump()
```

- [ ] **Step 3: Создать `src/tp/btorg/detail.py`**

```python
"""Детальный парсер btorg: фрагмент лотов -> пары таблицы лота и график снижения цены.

Какие лоты обходить, решает база (``MongoStorage.pending_detail``). Детали —
во фрагменте ``inner-view-lots.html`` торгов, по таблице на лот. Фрагмент
запрашивается один раз на торги (с признаком XHR), каждый ожидающий лот
получает свою таблицу.

Как и у iTender, детальный парсер — примесь к классу площадки: ``detail_of(Atctrade)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from tp.btorg.base import XHR, Btorg, lot_pairs, lot_tables, parse_schedule


def parse_details(page: Selector) -> dict[str, dict[str, Any]]:
    """Детали каждого лота фрагмента: номер лота -> пары и ``price_schedule``."""
    return {
        lot_num: {**lot_pairs(table), "price_schedule": parse_schedule(table)}
        for lot_num, table in lot_tables(page)
    }


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class BtorgDetail(Btorg):
    """Примесь: вместо листинга — фрагменты лотов торгов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            yield self.request(url, headers = XHR, metadata = {"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        details = parse_details(response.selector())
        for lot_id in response.metadata["lot_ids"]:
            # lot_id — «{trade_id}_{lot_num}», trade_id — одни цифры.
            lot_num = lot_id.partition("_")[2]
            if lot_num in details:
                yield {"lot_id": lot_id, "detail": details[lot_num]}
            else:
                await self.log(f"лота {lot_id} во фрагменте нет — детали не записаны")


def detail_of(platform: type[Btorg]) -> type[BtorgDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — фрагменты лотов."""
    return type(f"{platform.__name__} Detail", (BtorgDetail, platform), {"__module__": platform.__module__})
```

- [ ] **Step 4: Создать `src/tp/btorg/source.py`**

```python
"""Площадки на движке btorg (edoc-ETP)."""

from __future__ import annotations

from tp.btorg.base import Btorg


class Atctrade(Btorg):
    """Аукционный тендерный центр."""

    name = "atctrade"
    DOMAIN = "https://atctrade.ru"


class Ausib(Btorg):
    """Аукционы Сибири. Пускает только с cookie: первый ответ — редирект на тот же
    адрес, cookie хранит сессия фреймворка."""

    name = "ausib"
    DOMAIN = "https://ausib.ru"


class EtpProfit(Btorg):
    """ЭТП Профит. Соединения принимает через раз."""

    name = "etp_profit"
    DOMAIN = "https://etp-profit.ru"


class Aukcioncenter(Btorg):
    """Аукционный центр."""

    name = "aukcioncenter"
    DOMAIN = "https://aukcioncenter.ru"


class Regtorg(Btorg):
    """Региональная торговая площадка."""

    name = "regtorg"
    DOMAIN = "https://regtorg.com"


class PtpCenter(Btorg):
    """ПТП-Центр. Соединения принимает через раз."""

    name = "ptp_center"
    DOMAIN = "https://ptp-center.ru"


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Btorg]] = {
    cls.name: cls for cls in Btorg.__subclasses__() if cls.__module__ == __name__
}
```

- [ ] **Step 5: Проверить разбор на фикстурах**

Создать `$SCRATCH/check_btorg.py`:

```python
from pathlib import Path

from parsel import Selector

from core.lot import Lot
from tp.btorg.base import find_next_page, parse_listing, parse_lots
from tp.btorg.detail import parse_details
from tp.btorg.source import PLATFORMS

FIX = Path("tests/btorg/fixtures")
listing = Selector((FIX / "listing_atctrade.html").read_text(encoding="utf-8"))
trades = parse_listing(listing)
print("торгов", len(trades), trades[0])
print("следующая", find_next_page(listing, 1))

fragment = Selector((FIX / "lots_13147.html").read_text(encoding="utf-8"))
trade = next((t for t in trades if t["trade_id"] == "13147"), {"trade_id": "13147"})
for lot in parse_lots(fragment, trade):
    print(Lot(source="atctrade", lot_url="x", trade_url="x", **lot).model_dump())
details = parse_details(fragment)
print({num: (len(d) - 1, len(d["price_schedule"])) for num, d in details.items()})
print("площадки", sorted(PLATFORMS))
```

Run: `PYTHONPATH=src uv run python $SCRATCH/check_btorg.py`

Expected: `торгов` > 0; `следующая (2, '...list.html?page=2...')`; лоты с `description`, `price`, `price_value`; у лотов публичного предложения — `bids_end` из графика; в `details` — у каждого лота > 0 пар; 6 площадок. Пустое поле, которое `delete/btorg.py` на той же фикстуре заполнял, — ошибка переноса.

- [ ] **Step 6: ruff**

Run: `uv run ruff check src/tp/btorg`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/tp/btorg
git commit -m "btorg по образцу iTender: base, detail, source"
```

---

### Task 6: Движок rus-on

**Files:**
- Create: `src/tp/ruson/__init__.py` (пустой)
- Create: `src/tp/ruson/base.py`
- Create: `src/tp/ruson/detail.py`
- Create: `src/tp/ruson/source.py`
- Справочник: `src/tp/delete/ruson.py`, `src/tp/delete/ruson_platforms.py`
- Фикстуры: `tests/ruson/fixtures/listing_nistp.html`, `listing_rus_on.html`, `trade_496200.html`

- [ ] **Step 1: Создать пустой `src/tp/ruson/__init__.py`**

- [ ] **Step 2: Создать `src/tp/ruson/base.py`**

```python
"""Базовый парсер движка rus-on.

Листинги у площадок группы разные — ``table.data`` или ``table.node_view``,
ссылка на торги в ``<a href>`` или в ``onclick`` строки, строка на торги или на
лот, колонки в разном порядке. Одинакова только ссылка на торги
``trade_view.php?trade_nid=N``: по ней листинг сводится к торгам, а колонки
находятся по заголовку. Номер страницы — параметр ``pagenum`` (пейджер
выставляет его в форме через ``pagenum_send(N)``). Страница торгов у всех одна:
пары ``<td>подпись</td><td>значение</td>``, лоты — таблицы с заголовком
«Лот № N». Своей страницы у лота нет: его адрес — адрес торгов.

Площадка наследует ``Ruson`` и задаёт ``name`` и ``DOMAIN``, при другом пути
листинга — ``LISTING_PATH``.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import takewhile
from typing import Any, ClassVar

from collector import Crawler, Response, Settings
from parsel import Selector

from core.conf import conf
from core.help import clean, digits
from core.lot import Lot

#: Заголовки колонок листинга — части слов, в разных написаниях площадок.
COLUMNS = {
    "status": ("состояние", "статус"),
    "deadline": ("конец приема", "окончание приема", "окончания представ"),
    "organizer": ("организатор",),
    "debtor": ("должник",),
}
TRADE_VIEW = "trade_view.php?trade_nid="


def header(page: Selector) -> list[str]:
    """Заголовки колонок таблицы торгов — строка с наибольшим числом ``<th>``.

    Над таблицей у rus_on и promkonsalt стоит строка поиска со своим ``<th>``;
    считать все ``<th>`` страницы подряд значило бы сдвинуть номера колонок.
    """
    rows = page.xpath("//tr[th]")
    if not rows:
        return []
    widest = max(rows, key=lambda row: len(row.xpath("./th")))
    return [(clean(th.xpath("string(.)").get()) or "").lower() for th in widest.xpath("./th")]


def trade_code(text: str) -> str | None:
    """Видимый код торгов в строке: «70700-ОТПП» — цифры, дефис, от двух заглавных."""
    for word in text.split():
        head, _, tail = word.partition("-")
        letters = "".join(takewhile(str.isupper, tail))
        if head.isdigit() and len(letters) >= 2:
            return f"{head}-{letters}"
    return None


def parse_listing(page: Selector) -> list[dict[str, Any]]:
    """Страница листинга -> торги, без повторов внутри страницы (по ``trade_nid``).

    ``trade_id`` — цифры видимого кода торгов, если он есть, иначе внутренний
    ``trade_nid``. Сведения из колонок приблизительные: авторитетные берутся со
    страницы торгов.
    """
    headers = header(page)
    cols = {
        name: next((i for i, h in enumerate(headers) if any(n in h for n in needles)), None)
        for name, needles in COLUMNS.items()
    }
    trades = []
    seen: set[str] = set()
    rows = page.xpath(
        f'//tr[.//a[contains(@href, "{TRADE_VIEW}")]] | //tr[contains(@onclick, "{TRADE_VIEW}")]'
    )
    for row in rows:
        href = row.xpath(f'.//a[contains(@href, "{TRADE_VIEW}")]/@href').get()
        nid = digits((href or row.xpath("./@onclick").get() or "").split(TRADE_VIEW, 1)[-1])
        if not nid or nid in seen:
            continue
        seen.add(nid)
        cells = row.xpath("./td")

        def cell(name: str, cells: list[Selector] = cells) -> Selector | None:
            index = cols[name]
            return cells[index] if index is not None and index < len(cells) else None

        def text(name: str) -> str | None:
            node = cell(name)
            return clean(node.xpath("string(.)").get()) if node else None

        code = trade_code(clean(row.xpath("string(.)").get()) or "")
        debtor = cell("debtor")
        trades.append(
            {
                "trade_id": digits(code) if code else nid,
                "trade_number": code,
                "trade_type": code.split("-")[1] if code else None,
                # onclick без href: ссылка относительно листинга — там же, где он.
                "trade_url": href or f"{TRADE_VIEW}{nid}",
                "status": text("status"),
                "bids_end": text("deadline"),
                "organizer": text("organizer"),
                # Ячейка — «должник, предмет торгов»; имя должника — первая жирная строка.
                "debtor": clean(debtor.xpath('.//span[contains(@style, "bold")][1]/text()').get())
                if debtor
                else None,
            }
        )
    return trades


def find_next_page(page: Selector, num_page: int) -> int | None:
    """Следующий номер из пейджера ``pagenum_send(N)``; ``None`` — страница последняя."""
    numbers = (
        page.xpath('//ul[contains(@class, "pagination")]//a/@onclick[contains(., "pagenum_send(")]')
        .xpath('substring-before(substring-after(., "pagenum_send("), ")")')
        .getall()
    )
    later = [int(n) for n in numbers if n.isdigit() and int(n) > num_page]
    return min(later) if later else None


def field(scope: Selector, label: str) -> str | None:
    """Значение строки, первая ячейка которой содержит ``label``.

    Без привязки к классу: у большинства площадок подпись — ``td.label``, у
    promkonsalt — простой ``td``.
    """
    return clean(
        scope.xpath(f'.//tr[td[1][contains(normalize-space(.), "{label}")]]/td[2]').xpath("string(.)").get()
    )


def block(page: Selector, title: str) -> Selector:
    """Таблица раздела с заголовком ``title``; берётся самый внутренний элемент с этим
    текстом, иначе попалась бы внешняя таблица всей страницы."""
    node = page.xpath(
        f'//*[contains(normalize-space(.), "{title}")][not(.//*[contains(normalize-space(.), "{title}")])]'
    )
    return node.xpath("./ancestor::table[1]")


def debtor_of(page: Selector) -> str | None:
    """Должник из раздела «Информация о должнике»: ФИО или полное наименование."""
    section = block(page, "Информация о должнике")
    if not section:
        return None
    if "юридич" in (field(section, "Тип должника") or "").lower():
        return field(section, "Полное наименование") or field(section, "Наименование должника")
    names = (field(section, "Фамилия"), field(section, "Имя"), field(section, "Отчество"))
    return " ".join(p for p in names if p) or None


def organizer_of(page: Selector) -> str | None:
    """Организатор из «Информации об организаторе», иначе — его контактное лицо (promkonsalt)."""
    section = block(page, "Информация об организаторе")
    organizer = field(section, "Наименование") if section else None
    if not organizer and (contact := block(page, "Контактное лицо организатора")):
        organizer = field(contact, "ФИО")
    return organizer


def lot_tables(page: Selector) -> list[tuple[str, str, Selector]]:
    """Разделы «Лот № N»: номер лота, заголовок раздела и его таблица.

    Маркер лота — ``<th>`` или ``span.lot_title`` (promkonsalt), и только самый
    внутренний: фраза «Лот № 1» встречается и в тексте объявления, и без этого
    условия получался лот-призрак без цены.
    """
    markers = page.xpath(
        '//*[(self::th or contains(@class, "lot_title")) and contains(., "Лот №")'
        ' and not(descendant::*[contains(., "Лот №")])]'
    )
    tables = []
    for marker in markers:
        title = clean(marker.xpath("string(.)").get()) or ""
        if lot_num := digits(title.split("Лот №", 1)[1].strip()):
            tables.append((lot_num, title, marker.xpath("./ancestor::table[1]")))
    return tables


def lot_pairs(table: Selector) -> dict[str, str]:
    """Пары «подпись: значение» таблицы лота."""
    return {
        label.rstrip(":").strip(): value
        for row in table.xpath(".//tr[td[2]]")
        if (label := clean(row.xpath("string(./td[1])").get()))
        and (value := clean(row.xpath("string(./td[2])").get()))
    }


def parse_lots(page: Selector, trade: dict[str, Any]) -> list[dict[str, Any]]:
    """Разделы «Лот № N» страницы торгов -> поля ``Lot`` без ``source`` и адресов."""
    shared = {
        "trade_id": trade["trade_id"],
        "trade_number": trade.get("trade_number"),
        "trade_type": trade.get("trade_type"),
        "status": field(page, "Статус торгов") or trade.get("status"),
        "bids_end": field(page, "Дата окончания представления") or trade.get("bids_end"),
        "auction_date": field(page, "Дата проведения"),
        # Колонки листинга на части площадок пустые или захватывают список
        # лотов — раздел страницы торгов надёжнее.
        "organizer": organizer_of(page) or trade.get("organizer"),
        "debtor": debtor_of(page) or trade.get("debtor"),
    }
    return [
        {
            **shared,
            "lot_id": f"{trade['trade_id']}_{lot_num}",
            "lot_num": lot_num,
            "description": field(table, "Наименование")
            or (title.split(":", 1)[1].strip() if ":" in title else None),
            "price": field(table, "Начальная цена"),
        }
        for lot_num, title, table in lot_tables(page)
    ]


@dataclass(frozen=True)
class RusonParams:
    """Что задаётся на прогон: ``open_crawl(..., params={"max_pages": 5})``."""

    max_pages: int = conf.parsing.max_pages


class Ruson(Crawler):

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = "bankrot/trade_list.php"

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50,
    )
    params = RusonParams()

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Адрес листинга — из домена площадки. LISTING_PATH у части площадок
        # свой, поэтому пересобираем и тогда, когда задан только он.
        if "DOMAIN" in cls.__dict__ or "LISTING_PATH" in cls.__dict__:
            cls.start_urls = [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"]

    async def parse(self, response: Response) -> Any:
        """Страница листинга: зайти в каждые торги, затем следующая страница."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        page = response.selector()
        num_page = response.metadata.get("num_page") or 1
        trades = parse_listing(page)
        await self.log(f"страница {num_page}: торгов {len(trades)}")

        for trade in trades:
            yield response.follow(trade["trade_url"], callback = self.parse_trade, metadata = {"trade": trade})

        next_page = find_next_page(page, num_page)
        if next_page is None:
            await self.log(f"страница {num_page} последняя")
        elif num_page >= self.params.max_pages:
            await self.log(f"дошли до предела max_pages={self.params.max_pages}, дальше не листаем")
        else:
            yield self.request(
                self.start_urls[0], params = {"pagenum": next_page}, metadata = {"num_page": next_page}
            )

    async def parse_trade(self, response: Response) -> Any:
        """Страница торгов: по ``Lot`` на лот; адрес лота — адрес торгов."""
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        trade_url = response.request.url
        for lot in parse_lots(response.selector(), response.metadata["trade"]):
            yield Lot(source = self.name, lot_url = trade_url, trade_url = trade_url, **lot).model_dump()
```

Примечание к `__init_subclass__`: у `Sistematorg` и `Promkonsalt` `LISTING_PATH` задан в том же классе, что и `DOMAIN`, так что условие `"DOMAIN" in cls.__dict__` их тоже покрывает; `or "LISTING_PATH"` — на случай, если путь переопределят в наследнике площадки. Если `DOMAIN` при этом не задан ни в одном предке, будет `AttributeError` — так и надо: площадка без домена — ошибка объявления.

- [ ] **Step 3: Создать `src/tp/ruson/detail.py`**

```python
"""Детальный парсер rus-on: страница торгов -> пары таблицы лота.

Какие лоты обходить, решает база (``MongoStorage.pending_detail``). Детали —
на странице торгов, по таблице «Лот № N» на лот. Страница запрашивается один
раз на торги, каждый ожидающий лот получает свою таблицу.

Как и у iTender, детальный парсер — примесь к классу площадки: ``detail_of(Nistp)``.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any

from collector import Request, Response
from parsel import Selector

from tp.ruson.base import Ruson, lot_pairs, lot_tables


def parse_details(page: Selector) -> dict[str, dict[str, Any]]:
    """Детали каждого лота страницы торгов: номер лота -> пары его таблицы."""
    return {lot_num: lot_pairs(table) for lot_num, _, table in lot_tables(page)}


@dataclass(frozen=True)
class DetailParams:
    """Сколько лотов обойти за прогон: первый прогон по всей базе был бы долгим."""

    limit: int = 100


class RusonDetail(Ruson):
    """Примесь: вместо листинга — страницы торгов лотов, ждущих деталей."""

    params = DetailParams()

    async def start_requests(self) -> AsyncIterator[Request]:
        lots = [lot async for lot in self.ctx.sink.pending_detail(self.params.limit)]
        await self.log(f"ждут деталей: {len(lots)} (не больше {self.params.limit})")
        trades: dict[str, list[str]] = defaultdict(list)
        for lot in lots:
            trades[lot.get("trade_url") or lot["lot_url"]].append(lot["lot_id"])
        for url, lot_ids in trades.items():
            yield self.request(url, metadata = {"lot_ids": lot_ids})

    async def parse(self, response: Response) -> Any:
        if response.status != 200:
            raise ValueError(f"{response.status} для {response.request.url}")
        details = parse_details(response.selector())
        for lot_id in response.metadata["lot_ids"]:
            # lot_id — «{trade_id}_{lot_num}», trade_id — одни цифры.
            lot_num = lot_id.partition("_")[2]
            if lot_num in details:
                yield {"lot_id": lot_id, "detail": details[lot_num]}
            else:
                await self.log(f"лота {lot_id} на странице торгов нет — детали не записаны")


def detail_of(platform: type[Ruson]) -> type[RusonDetail]:
    """Детальный парсер площадки: её имя и настройки, разбор — страницы торгов."""
    return type(f"{platform.__name__} Detail", (RusonDetail, platform), {"__module__": platform.__module__})
```

- [ ] **Step 4: Создать `src/tp/ruson/source.py`**

```python
"""Площадки на движке rus-on."""

from __future__ import annotations

from tp.ruson.base import Ruson


class Nistp(Ruson):
    """Новые информационные сервисы."""

    name = "nistp"
    DOMAIN = "https://nistp.ru"


class ElTorg(Ruson):
    """Электронные торги."""

    name = "el_torg"
    DOMAIN = "https://el-torg.com"


class RusOn(Ruson):
    """РОССИЯ ОнЛайн."""

    name = "rus_on"
    DOMAIN = "https://rus-on.ru"


class Sistematorg(Ruson):
    """Объединённые системы торгов. Листинг в корне сайта, а не в ``bankrot/``."""

    name = "sistematorg"
    DOMAIN = "https://sistematorg.com"
    LISTING_PATH = "tradelist.php"


class Promkonsalt(Ruson):
    """Промконсалт. Листинг в корне сайта, а не в ``bankrot/``."""

    name = "promkonsalt"
    DOMAIN = "https://promkonsalt.ru"
    LISTING_PATH = "tradelist.php"


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Ruson]] = {
    cls.name: cls for cls in Ruson.__subclasses__() if cls.__module__ == __name__
}
```

- [ ] **Step 5: Проверить разбор на фикстурах**

Создать `$SCRATCH/check_ruson.py`:

```python
from pathlib import Path

from parsel import Selector

from core.lot import Lot
from tp.ruson.base import find_next_page, parse_listing, parse_lots
from tp.ruson.detail import parse_details
from tp.ruson.source import PLATFORMS

FIX = Path("tests/ruson/fixtures")
for name in ("listing_nistp.html", "listing_rus_on.html"):
    listing = Selector((FIX / name).read_text(encoding="utf-8"))
    trades = parse_listing(listing)
    print(name, "торгов", len(trades), trades[0] if trades else None, "следующая", find_next_page(listing, 1))

trade_page = Selector((FIX / "trade_496200.html").read_text(encoding="utf-8"))
for lot in parse_lots(trade_page, {"trade_id": "496200"}):
    print(Lot(source="rus_on", lot_url="x", trade_url="x", **lot).model_dump())
print({num: len(d) for num, d in parse_details(trade_page).items()})
print({name: cls.start_urls for name, cls in PLATFORMS.items()})
```

Run: `PYTHONPATH=src uv run python $SCRATCH/check_ruson.py`

Expected: в обоих листингах `торгов` > 0; для rus_on — `следующая 2`; лоты с `price`, `price_value`, `organizer`, `debtor`; в деталях > 0 пар на лот; `start_urls` у sistematorg и promkonsalt оканчиваются на `/tradelist.php`, у остальных — на `/bankrot/trade_list.php`.

- [ ] **Step 6: ruff**

Run: `uv run ruff check src/tp/ruson`
Expected: `All checks passed!`

- [ ] **Step 7: Commit**

```bash
git add src/tp/ruson
git commit -m "rus-on по образцу iTender: base, detail, source"
```

---

### Task 7: Живой прогон

Цель — убедиться, что без фильтра статуса листинг листается (у kendo и btorg — по ссылкам пейджера, у rus-on — GET с `pagenum`), лоты доходят до Mongo, а detail находит свои лоты. Пишем в отдельные коллекции `smoke_<движок>`, чтобы не смешивать с рабочими данными.

**Files:**
- Create: `$SCRATCH/smoke.py` (в репозиторий не добавляется)

- [ ] **Step 1: Поднять Mongo**

Run: `docker compose up -d` и `docker compose ps`
Expected: сервис `mongo` в состоянии `healthy`.

- [ ] **Step 2: Создать `$SCRATCH/smoke.py`**

```python
"""Живой прогон: base с max_pages=1, затем detail с limit=5, по площадке на движок.

    PYTHONPATH=src uv run python smoke.py trade_alliance atctrade rus_on
"""

import asyncio
import logging
import sys
from datetime import UTC, datetime

from core.deps import open_run
from tp.btorg import detail as btorg_detail
from tp.btorg.base import BtorgParams
from tp.btorg.source import PLATFORMS as BTORG
from tp.kendo import detail as kendo_detail
from tp.kendo.base import KendoParams
from tp.kendo.source import PLATFORMS as KENDO
from tp.ruson import detail as ruson_detail
from tp.ruson.base import RusonParams
from tp.ruson.source import PLATFORMS as RUSON

ENGINES = {
    "kendo": (KENDO, KendoParams, kendo_detail),
    "btorg": (BTORG, BtorgParams, btorg_detail),
    "ruson": (RUSON, RusonParams, ruson_detail),
}


async def smoke(name: str) -> None:
    engine, (platforms, params_cls, detail) = next(
        (engine, spec) for engine, spec in ENGINES.items() if name in spec[0]
    )
    platform = platforms[name]
    short = type(platform.__name__, (platform,), {"params": params_cls(max_pages=1), "__module__": platform.__module__})
    collection = f"smoke_{engine}"

    async with open_run(collection, short) as run:
        new = sum([await run.storage.upsert(item) async for item in run.crawl.stream()])
        s = run.crawl.stats
        await run.log(f"base: лотов {s.items}, новых {new}, в базе {await run.storage.count()}, ошибок {s.errors} ({s.reason})")

    at = datetime.now(UTC)
    limited = type(platform.__name__, (detail.detail_of(platform),), {"params": detail.DetailParams(limit=5), "__module__": platform.__module__})
    async with open_run(collection, limited) as run:
        done = 0
        async for item in run.crawl.stream():
            await run.storage.save_detail(item["lot_id"], item["detail"], at)
            done += 1
        s = run.crawl.stats
        await run.log(f"detail: деталей {done}, ошибок {s.errors} ({s.reason})")


async def main(names: list[str]) -> None:
    for name in names:
        await smoke(name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    asyncio.run(main(sys.argv[1:]))
```

- [ ] **Step 3: Прогнать по площадке каждого движка**

Run: `PYTHONPATH=src uv run python $SCRATCH/smoke.py trade_alliance atctrade rus_on`

Expected для каждой площадки: строка `base: лотов N` с N > 0 и `ошибок 0` (или единицы на отдельных торгах); строка `detail: деталей M` с 0 < M ≤ 5. Если листинг дал `торгов 0` — площадка без фильтра отдаёт другую разметку; сохранить страницу (`response.text`) в scratchpad и сверить с фикстурой. Если у rus-on вторая страница не приходит — проверить, принимает ли площадка `pagenum` GET-параметром; прогон с `max_pages=2` это покажет.

- [ ] **Step 4: Посмотреть документ глазами**

Run:
```bash
docker compose exec mongo mongosh trading --quiet --eval 'db.smoke_kendo.findOne({detail: {$exists: true}})'
```
Expected: документ с полями `Lot` (включая `price_value`, `bids_end_at`, `is_active`), `created_at`, `updated_at`, `detail` (пары и `attachments`), `detail_at`. То же для `smoke_btorg`, `smoke_ruson`.

- [ ] **Step 5: Прибрать**

Run:
```bash
docker compose exec mongo mongosh trading --quiet --eval 'db.smoke_kendo.drop(); db.smoke_btorg.drop(); db.smoke_ruson.drop()'
```

- [ ] **Step 6: Итоговая проверка**

Run: `uv run ruff check src/core src/tp/kendo src/tp/btorg src/tp/ruson` и `git status`
Expected: `All checks passed!`; рабочее дерево чистое, `src/tp/itender/` и `src/tp/delete/` в `git diff 102e2ec --stat` (коммит спеки) не фигурируют.
