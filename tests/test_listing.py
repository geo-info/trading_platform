"""Листинг: сброс фильтра, пагинация и окно по дате — через настоящий ``parse()``.

Фикстура — настоящий листинг centerr: он открывается с фильтром «Прием заявок»
и пейджером на следующие страницы. Тесты гоняют ``parse()`` площадки на этой
странице и смотрят, какой запрос он отдаёт, — тело формы собирает
``Response.form_request()`` фреймворка, как собрал бы браузер.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from collector import CrawlerContext, Request, Response
from parsel import Selector

from tp.common import older_than
from tp.marking.fogsoft import find_next_target
from tp.platforms.fogsoft.centerr import Centerr

LISTING = (Path(__file__).parent / "fixtures" / "centerr_listing.html").read_text(encoding="utf-8")
#: Тот же листинг, но без фильтра: в «Статусе» выбрано «Все».
UNFILTERED = LISTING.replace('<option value="7" selected>', '<option value="7">')
URL = Centerr.start_urls[0]
PANEL = "ctl00$ctl00$MainExpandableArea$phExpandCollapse$"
STATUS = PANEL + "PurchasesSearchCriteria$vPurchaseLot_purchaseStatusID_Статус"
SEARCH = PANEL + "SearchButton"


async def parse(html: str, **metadata: Any) -> list[Request]:
    crawler = Centerr(CrawlerContext(http=None))
    page = Response(SimpleNamespace(status_code=200, text=html), Request(url=URL, metadata=metadata), crawler)
    return [out async for out in crawler.parse(page)]


def fields(request: Request) -> dict[str, str]:
    assert isinstance(request.data, list), "тело формы — пары (имя, значение)"
    return dict(request.data)


# ── сброс фильтра ────────────────────────────────────────────────────────────


async def test_фильтр_статуса_сбрасывается_поиском_с_все() -> None:
    (request,) = await parse(LISTING)  # строки отфильтрованной страницы не берём
    body = fields(request)
    assert (request.method, request.url) == ("POST", URL)
    assert body[STATUS] == ""
    assert body[SEARCH] == "Искать торги"
    assert body["__CVIEWSTATE"] and body["__EVENTVALIDATION"]
    # Нажата только кнопка поиска: «Очистить» и «Войти» не отправляются.
    assert not any(name.endswith(("ClearButton", "Login")) for name in body)
    assert request.metadata == {"page": 1, "filters_reset": True}


async def test_без_фильтра_поиск_не_отправляется() -> None:
    requests = await parse(UNFILTERED)
    assert not any(r.method == "POST" and SEARCH in fields(r) for r in requests)


async def test_после_сброса_страница_не_сбрасывается_снова() -> None:
    """Иначе обход крутился бы на первой странице, пока не кончатся запросы."""
    requests = await parse(LISTING, filters_reset=True)
    assert not any(r.method == "POST" and SEARCH in fields(r) for r in requests)


# ── пагинация ────────────────────────────────────────────────────────────────


async def test_следующая_страница_это_postback_пейджера() -> None:
    requests = await parse(UNFILTERED)
    lots = [r for r in requests if r.method == "GET"]
    (pager,) = [r for r in requests if r.method == "POST"]
    body = fields(pager)

    assert len(lots) == 20
    assert pager.url == URL and pager.metadata == {"page": 2}
    assert body["__EVENTTARGET"] == find_next_target(Selector(UNFILTERED), 1)
    assert body["__EVENTARGUMENT"] == ""
    assert body["__CVIEWSTATE"] and body["__EVENTVALIDATION"]
    # Форма уходит целиком, как у браузера, но без нажатой кнопки поиска.
    assert body[STATUS] == ""
    assert SEARCH not in body


async def test_без_токенов_страницы_цепочка_не_продолжается() -> None:
    """Пост без __CVIEWSTATE сервер ответит первой страницей — обрыв выдал бы себя за конец."""
    broken = UNFILTERED.replace('name="__CVIEWSTATE"', 'name="__GONE"')
    requests = await parse(broken)
    assert not [r for r in requests if r.method == "POST"]


# ── окно обхода по дате ──────────────────────────────────────────────────────


def test_страница_старая_только_если_старая_вся() -> None:
    since = date(2026, 1, 1)
    assert older_than(["31.12.2025 18:00", "01.06.2025 10:00"], since) is True
    # Одна свежая строка держит обход: порядок по номеру торгов, не по сроку.
    assert older_than(["31.12.2025 18:00", "02.01.2026 10:00 (5 дн.)"], since) is False
    # Без дат решать не на чем — листаем дальше.
    assert older_than([None, None], since) is False
    assert older_than([], since) is False
