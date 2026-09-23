"""Листинг: сброс фильтра, с которым площадка его открывает.

centerr по умолчанию показывает только «Прием заявок» — без сброса в базу не
попадал ни один завершённый лот. Фикстура — его настоящий листинг.
"""

from __future__ import annotations

from pathlib import Path

from parsel import Selector

from tp.base import filter_reset_payload

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
