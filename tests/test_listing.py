"""Листинг: сброс фильтра, с которым площадка его открывает, и окно по дате.

centerr по умолчанию показывает только «Прием заявок» — без сброса в базу не
попадал ни один завершённый лот. Фикстура — его настоящий листинг.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

from parsel import Selector

from tp.base import filter_reset_payload, page_is_older

LISTING = (Path(__file__).parent / "fixtures" / "centerr_listing.html").read_text(encoding="utf-8")
STATUS = "ctl00$ctl00$MainExpandableArea$phExpandCollapse$PurchasesSearchCriteria$vPurchaseLot_purchaseStatusID_Статус"


def test_фильтр_статуса_сбрасывается_на_все() -> None:
    payload = filter_reset_payload(Selector(LISTING))
    assert payload is not None
    assert payload[STATUS] == ""
    assert payload["ctl00$ctl00$MainExpandableArea$phExpandCollapse$SearchButton"] == "Искать торги"
    assert payload["__CVIEWSTATE"] and payload["__EVENTVALIDATION"]
    # «Очистить» и форма входа в запрос не попадают.
    assert not any("ClearButton" in name or "Login" in name for name in payload)


def test_без_фильтра_ничего_не_отправляется() -> None:
    unfiltered = LISTING.replace('<option value="7" selected>', '<option value="7">')
    assert unfiltered != LISTING
    assert filter_reset_payload(Selector(unfiltered)) is None


# ── окно обхода по дате ──────────────────────────────────────────────────────


def rows(*deadlines: str | None) -> list[dict]:
    return [{"bids_end": d} for d in deadlines]


def test_страница_старая_только_если_старая_вся() -> None:
    since = date(2026, 1, 1)
    assert page_is_older(rows("31.12.2025 18:00", "01.06.2025 10:00"), since) is True
    # Одна свежая строка держит обход: порядок по номеру торгов, не по сроку.
    assert page_is_older(rows("31.12.2025 18:00", "02.01.2026 10:00 (5 дн.)"), since) is False
    # Без дат решать не на чем — листаем дальше.
    assert page_is_older(rows(None, None), since) is False
    assert page_is_older([], since) is False
