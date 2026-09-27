"""Итог проверки лота: сверки, незнакомые подписи, запасной документ."""

from __future__ import annotations

from pathlib import Path

import pytest
from parsel import Selector

from core.known_labels import KNOWN_LABELS, unknown_labels
from tp.base import FogsoftLot, build_item

FIXTURES = Path(__file__).parent / "fixtures"
LOT = "Информация о лоте"

#: Строка листинга, согласованная со страницей tendergarant 19208.
ROW = {
    "lot_url": "/public/auctions/lots/view/19208/",
    "trade_id": "0004521",
    "auction_name": "Продажа имущества",
    "lot_num": "1",
    "description": "Жилое помещение",
    "price": "533 293,04",
    "organizer": "Организатор",
    "bids_end": "14.10.2026 18:00 (21 дн.)",
    "auction_date": "22.10.2026 12:00",
    "status": "Приём заявок",
    "winner": None,
    "trade_type": "Открытый аукцион с открытой формой представления цены",
}
PAGE = Selector((FIXTURES / "tendergarant_lot_19208.html").read_text(encoding="utf-8"))


def item(**row: object) -> dict:
    return build_item("tendergarant", "19208", "https://tendergarant.com/x", {**ROW, **row}, PAGE)


def errors(**row: object) -> list[str]:
    return item(**row)["validation"]["errors"]


def test_согласованный_лот_проходит() -> None:
    result = item()
    assert result["validation"] == {"ok": True, "errors": [], "unknown_labels": []}


# ── сверки, каждая на своём подменённом значении ─────────────────────────────


def test_цена_листинга_не_равна_цене_страницы() -> None:
    (error,) = errors(price="1 000,00")
    assert error.startswith("цена листинга 1000.0")


def test_цена_сравнивается_числом_а_не_строкой() -> None:
    assert errors(price="533293,04") == []


def test_статус_листинга_не_равен_статусу_страницы() -> None:
    (error,) = errors(status="Окончен")
    assert "status_raw" in error and "Окончен" in error


def test_номер_лота_листинга_не_равен_номеру_страницы() -> None:
    (error,) = errors(lot_num="2")
    assert "lot_num" in error


def test_аукцион_приём_заявок_позже_торгов() -> None:
    (error,) = errors(bids_end="23.10.2026 18:00")
    assert error.startswith("приём заявок до 23.10.2026 18:00 позже торгов")


def test_у_публичного_предложения_сроки_не_сверяются() -> None:
    assert errors(bids_end="23.10.2026 18:00", trade_type="Открытое публичное предложение") == []


@pytest.mark.parametrize(
    "label", ["Номер", "Наименование", "Статус", "Начальная цена, руб.", "Классификатор ЕФРСБ"]
)
def test_обязательное_поле_страницы_лота(label: str) -> None:
    good = item()
    detail = {**good["extra"], LOT: {k: v for k, v in good["extra"][LOT].items() if k != label}}
    lot = FogsoftLot.model_validate({**good, "extra": detail})
    assert f"нет «{label}» в «{LOT}»" in lot.validation["errors"]
    assert lot.validation["ok"] is False


# ── реестр подписей ──────────────────────────────────────────────────────────


def test_незнакомая_подпись_не_влияет_на_ok() -> None:
    good = item()
    detail = {**good["extra"], LOT: {**good["extra"][LOT], "Цвет лота": "синий"}, "Новый раздел": {"А": "б"}}
    lot = FogsoftLot.model_validate({**good, "extra": detail})
    assert lot.validation["unknown_labels"] == [f"{LOT} :: Цвет лота", "Новый раздел :: *"]
    assert lot.validation["ok"] is True


def test_все_подписи_фикстур_известны() -> None:
    """Реестр строился по выгрузке — страницы фикстур в нём должны узнаваться."""
    assert item()["validation"]["unknown_labels"] == []
    assert all(isinstance(labels, frozenset) and labels for labels in KNOWN_LABELS.values())
    assert unknown_labels({}) == []


# ── запасной документ ────────────────────────────────────────────────────────


def test_лот_который_модель_не_пропустила_сохраняется() -> None:
    """Без номера торгов Lot не собирается — раньше такой лот терялся целиком."""
    result = item(trade_id=None)
    assert (result["source"], result["lot_id"], result["url"]) == (
        "tendergarant",
        "19208",
        "https://tendergarant.com/x",
    )
    assert result["row"]["trade_id"] is None
    assert result["validation"]["ok"] is False
    assert result["validation"]["errors"][0].startswith("модель:")
    assert "trade_id" in result["validation"]["errors"][0]
