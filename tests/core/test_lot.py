"""Модель ``core.lot.Lot`` и разбор значений из ``core.help``."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from parsel import Selector
from pydantic import ValidationError

from core.help import MSK, parse_datetime, parse_price
from core.lot import Lot, is_active_status
from tp.itender.base import parse_rows

FOGSOFT = Path(__file__).parents[1] / "fogsoft" / "fixtures"


def test_цена() -> None:
    assert parse_price("1 234 567,89") == 1234567.89
    assert parse_price("135 000.00") == 135000.0
    assert parse_price("280 000,00 руб, НДС не облагается") == 280000.0
    assert parse_price("Купить с агентом") is None
    assert parse_price(None) is None


def test_дата_по_москве_без_хвоста_дней() -> None:
    moment = parse_datetime("28.10.2026 10:00 (34 дн.)")
    assert moment == datetime(2026, 10, 28, 10, 0, tzinfo=MSK)
    assert moment.utcoffset().total_seconds() == 3 * 3600
    assert parse_datetime("10.09.2026") == datetime(2026, 9, 10, tzinfo=MSK)
    assert parse_datetime("когда-нибудь") is None


@pytest.mark.parametrize(
    ("status", "active"),
    [
        ("Прием заявок", True),
        ("Приём заявок на интервале не активен", True),
        ("Окончен", False),
        ("Не состоялся", False),
        ("Торги по лоту отменены", False),
        ("приём заявок завершен", False),
        (None, True),
    ],
)
def test_активность_по_статусу(status: str | None, active: bool) -> None:
    assert is_active_status(status) is active


def test_лот_хранит_строки_площадки_и_разобранные_значения() -> None:
    lot = Lot(
        source="bep",
        lot_id="1",
        lot_url="https://bankruptcy.bepspb.ru/public/lots/view/1/",
        price="270 000,00",
        bids_end="14.10.2026 18:00 (21 дн.)",
        status="Окончен",
    ).model_dump()
    assert (lot["price"], lot["price_value"]) == ("270 000,00", 270000.0)
    assert lot["bids_end_at"] == datetime(2026, 10, 14, 18, 0, tzinfo=MSK)
    assert (lot["auction_at"], lot["is_active"]) == (None, False)


def test_незнакомое_поле_и_лот_без_ключа_это_ошибка() -> None:
    with pytest.raises(ValidationError):
        Lot(source="bep", lot_id="1", lot_url="https://x", лишнее=1)
    with pytest.raises(ValidationError):
        Lot(source="bep", lot_url="https://x")


def test_строка_листинга_itender_ложится_в_модель_как_есть() -> None:
    """Поля модели названы как у листинга iTender — его айтем подходит без переделки."""
    page = Selector((FOGSOFT / "listing_centerr.html").read_text(encoding="utf-8"))
    rows = parse_rows(page)
    assert rows
    for row in rows:
        Lot(source="centerr", lot_id=row["lot_url"].rstrip("/").rsplit("/", 1)[-1], **row)
