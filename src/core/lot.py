"""Lot — типизированный айтем, который отдаёт каждый парсер.

Перенесено из coll-temp (``collector/core/lot.py``). Модель тонкая: типизирован
только листинг — цена и два срока (сырые строки остаются рядом), ``is_active``
выводится из статуса. Страница лота целиком лежит в ``extra`` как есть.
Незнакомые поля запрещены, чтобы дрейф разбора всплывал сразу.

Отличия от оригинала: поля ``url``, ``fetched_at`` и ``winner``, которых там
не было; статус сведён к одному написанию (сырой — в ``status_raw``); сроки —
по Москве, а не наивные.

Итог проверки лежит в самом документе, в ``validation``: чем лот противоречит
сам себе (``problems``) и какие подписи страницы движку незнакомы
(``unknown``). Расхождение — строка в ``errors``, а не исключение: лот с кривым
полем полезен целиком, а исключение стоило бы его потери. Своё движок
дописывает в наследнике — см. ``tp.fogsoft.FogsoftLot``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from core.parsing import is_active_status, normalize_status, parse_datetime


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
        errors = self.problems()
        self.validation = {"ok": not errors, "errors": errors, "unknown_labels": self.unknown()}
        return self

    def problems(self) -> list[str]:
        """Чем лот противоречит сам себе. Движок дописывает свои сверки.

        Общая — одна: у аукциона приём заявок не может кончиться позже торгов.
        """
        if (
            self.trade_type
            and "аукцион" in self.trade_type.lower()
            and self.bidding_deadline
            and self.result_date
            and self.bidding_deadline > self.result_date
        ):
            return [f"приём заявок до {self.bidding_date_raw} позже торгов {self.event_date_raw}"]
        return []

    def unknown(self) -> list[str]:
        """Подписи страницы, которых движок не знает. Без реестра — никаких."""
        return []
