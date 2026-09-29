"""Модель лота: вычисляемые поля попадают в документ, лишние поля — ошибка."""

from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from core.help import MSK
from core.lot import Lot, is_active_status

BASE = {"source": "bep", "lot_id": "1_1", "lot_url": "https://x/lot/1"}


def test_вычисляемые_поля_в_документе() -> None:
    doc = Lot(
        **BASE,
        price="1 000,50",
        bids_end="01.10.2026 12:00",
        auction_date="02.10.2026",
        status="Прием заявок",
    ).model_dump()
    assert doc["price_value"] == 1000.5
    assert doc["bids_end_at"] == datetime(2026, 10, 1, 12, 0, tzinfo=MSK)
    assert doc["auction_at"] == datetime(2026, 10, 2, tzinfo=MSK)
    assert doc["is_active"] is True
    assert doc["price"] == "1 000,50"


def test_пустой_лот_разбирается_в_none() -> None:
    doc = Lot(**BASE).model_dump()
    assert (doc["price_value"], doc["bids_end_at"], doc["auction_at"], doc["is_active"]) == (
        None,
        None,
        None,
        True,
    )


@pytest.mark.parametrize(
    ("status", "active"),
    [
        ("Прием заявок", True),
        ("Приём заявок", True),
        ("Идут торги", True),
        (None, True),
        ("что-то новое", True),
        ("Торги завершены", False),
        ("Торги отменены", False),
        ("Торги не состоялись", False),
        ("Признаны несостоявшимися", False),
        ("Прием заявок окончен", False),
        ("Торги приостановлены", False),
    ],
)
def test_is_active_status(status: str | None, active: bool) -> None:
    assert is_active_status(status) is active


def test_лишнее_поле_ошибка() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Lot(**BASE, typo="x")


def test_лот_неизменяем() -> None:
    lot = Lot(**BASE)
    with pytest.raises(ValidationError):
        lot.price = "1"
