"""Lot — типизированный айтем, который отдаёт каждый парсер.

Перенесено из coll-temp (``collector/core/lot.py``). Модель тонкая: типизирован
только листинг — цена и два срока (сырые строки остаются рядом), ``is_active``
выводится из статуса. Страница лота целиком лежит в ``extra`` как есть.
Незнакомые поля запрещены, чтобы дрейф разбора всплывал сразу.

Отличия от оригинала: поля ``url``, ``fetched_at`` и ``winner``, которых там
не было; статус сведён к одному написанию (сырой — в ``status_raw``); сроки —
по Москве, а не наивные.

Итог проверки лежит в самом документе, в ``validation``: сверки листинга со
страницей лота (``check``) и незнакомые подписи страницы
(``core.known_labels``). Расхождение — строка в ``errors``, а не исключение:
лот с кривым полем полезен целиком, а исключение стоило бы его потери.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.known_labels import unknown_labels
from core.parsing import is_active_status, normalize_status, parse_datetime, parse_price

#: Раздел страницы, с которым сверяется листинг.
LOT_SECTION = "Информация о лоте"
#: Без этих полей страница лота — не страница лота: разбор промахнулся.
REQUIRED = ("Номер", "Наименование", "Статус", "Начальная цена, руб.", "Классификатор ЕФРСБ")


class Lot(BaseModel):
    """Один лот торгов, одинаковый для всех площадок."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    source: str = Field(alias="_source")
    lot_id: str
    trade_id: str
    lot_num: str | None = None
    url: str | None = None
    fetched_at: str | None = None

    trade_number: str | None = None
    trade_type: str | None = None
    debtor: str | None = None
    organizer: str | None = None
    winner: str | None = None

    description: str | None = None
    lot_url: str | None = None
    price: float | None = None
    price_raw: str | None = None

    status: str | None = None
    status_raw: str | None = None
    is_active: bool = True
    bidding_deadline: datetime | None = None
    result_date: datetime | None = None
    bidding_date_raw: str | None = None
    event_date_raw: str | None = None

    attachments: list[dict[str, Any]] = Field(default_factory=list)
    price_schedule: list[dict[str, Any]] = Field(default_factory=list)
    #: «Причина отказа победителя (ФИО)» со страницы лота: {role, party, reason}.
    refusals: list[dict[str, Any]] = Field(default_factory=list)
    extra: dict[str, Any] = Field(default_factory=dict, alias="detail")
    #: {ok, errors, unknown_labels}; ``ok`` зависит только от ``errors``.
    validation: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="before")
    @classmethod
    def _normalize(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        d = dict(data)
        if "bidding_date" in d:
            d["bidding_date_raw"] = d.get("bidding_date")
            d["bidding_deadline"] = parse_datetime(d.pop("bidding_date"))
        if "event_date" in d:
            d["event_date_raw"] = d.get("event_date")
            d["result_date"] = parse_datetime(d.pop("event_date"))
        if "status" in d:
            d["status_raw"] = d.get("status")
            d["status"] = normalize_status(d["status"])
        d.setdefault("is_active", is_active_status(d.get("status")))
        return d

    @model_validator(mode="after")
    def _validate(self) -> Lot:
        errors = check(self)
        self.validation = {"ok": not errors, "errors": errors, "unknown_labels": unknown_labels(self.extra)}
        return self


def check(lot: Lot) -> list[str]:
    """Сверки листинга со страницей лота: чем они расходятся.

    Листинг и страница — два разбора одного лота, и расхождение между ними
    почти всегда ошибка разбора, а не площадки: так нашёлся сдвиг пар на
    tendergarant, где «Начальная цена» съехала в «Шаг».
    """
    page = lot.extra.get(LOT_SECTION) or {}
    errors = [f"нет «{label}» в «{LOT_SECTION}»" for label in REQUIRED if not page.get(label)]

    # Цена листинга — это начальная цена лота или, у публичного предложения,
    # текущая. Сравниваются числа: строки расходятся пробелами.
    prices = [
        p for label in ("Начальная цена, руб.", "Текущая цена, руб.") if (p := parse_price(page.get(label)))
    ]
    if lot.price is not None and prices and not any(abs(lot.price - p) < 0.005 for p in prices):
        errors.append(f"цена листинга {lot.price} не равна ни начальной, ни текущей {prices}")

    for field, label in (("status_raw", "Статус"), ("lot_num", "Номер")):
        listing, detail = getattr(lot, field), page.get(label)
        if listing and detail and listing != detail:
            errors.append(f"{field} листинга «{listing}» ≠ «{label}» страницы «{detail}»")

    if (
        lot.trade_type
        and "аукцион" in lot.trade_type.lower()
        and lot.bidding_deadline
        and lot.result_date
        and lot.bidding_deadline > lot.result_date
    ):
        errors.append(f"приём заявок до {lot.bidding_date_raw} позже торгов {lot.event_date_raw}")
    return errors
