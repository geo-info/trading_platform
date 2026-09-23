"""Модель ``Lot`` и разбор значений, перенесённые из coll-temp."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest
from parsel import Selector
from pydantic import ValidationError

from core.lot import Lot
from core.parsing import MSK, is_active_status, normalize_status, parse_datetime, parse_price
from tp.base import parse_attachments, parse_price_schedule

FIXTURES = Path(__file__).parent / "fixtures"


def page(name: str) -> Selector:
    return Selector((FIXTURES / name).read_text(encoding="utf-8"))


def test_цена() -> None:
    assert parse_price("1 234 567,89") == 1234567.89
    assert parse_price("280 000,00 руб, НДС не облагается") == 280000.0
    assert parse_price("Купить с агентом") is None


def test_дата_без_хвоста_дней() -> None:
    moment = parse_datetime("28.10.2026 10:00 (34 дн.)")
    assert moment == datetime(2026, 10, 28, 10, 0, tzinfo=MSK)
    assert moment.utcoffset().total_seconds() == 3 * 3600
    assert parse_datetime("10.09.2026") == datetime(2026, 9, 10, tzinfo=MSK)
    assert parse_datetime("когда-нибудь") is None


@pytest.mark.parametrize(
    ("status", "active"),
    [
        ("Прием заявок", True),
        ("Приём заявок", True),
        ("Окончен", False),
        ("Не состоялся", False),
        (None, True),
    ],
)
def test_активность_по_статусу(status: str | None, active: bool) -> None:
    assert is_active_status(status) is active


def test_lot_разбирает_сроки_и_хранит_сырые_строки() -> None:
    lot = Lot.model_validate(
        {
            "source": "bep",
            "lot_id": "1",
            "trade_id": "0001",
            "status": "Окончен",
            "bidding_date": "14.10.2026 18:00 (21 дн.)",
            "event_date": "22.10.2026 12:00",
            "detail": {"Информация о лоте": {"Номер": "1"}},
        }
    )
    assert lot.bidding_deadline == datetime(2026, 10, 14, 18, 0, tzinfo=MSK)
    assert lot.bidding_date_raw == "14.10.2026 18:00 (21 дн.)"
    assert lot.result_date == datetime(2026, 10, 22, 12, 0, tzinfo=MSK)
    assert lot.is_active is False
    assert lot.model_dump()["extra"] == {"Информация о лоте": {"Номер": "1"}}


def test_lot_не_принимает_незнакомые_поля() -> None:
    with pytest.raises(ValidationError):
        Lot.model_validate({"source": "bep", "lot_id": "1", "trade_id": "0001", "лишнее": 1})


def test_документы_лота() -> None:
    attachments = parse_attachments(page("tendergarant_lot_19208.html"))
    assert attachments
    assert all(a["url"] and a["name"] for a in attachments)
    assert all(isinstance(a["signed"], bool) for a in attachments)


def test_график_снижения_цены_только_у_публичного_предложения() -> None:
    schedule = parse_price_schedule(page("centerr_lot_1170194.html"))
    assert schedule and all(len(row) > 1 for row in schedule)
    assert parse_price_schedule(page("tendergarant_lot_19208.html")) == []


def test_статус_сводится_к_одному_написанию() -> None:
    assert normalize_status("Прием заявок") == normalize_status("Приём заявок") == "Приём заявок"
    lot = Lot.model_validate({"source": "bep", "lot_id": "1", "trade_id": "1", "status": "Прием заявок"})
    assert (lot.status, lot.status_raw, lot.is_active) == ("Приём заявок", "Прием заявок", True)
