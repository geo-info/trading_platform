"""Чистые переходы состояния лота; сетевых запросов и Mongo здесь нет."""

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from core.trade_type import detail_type_info, normalize_trade_type, resolve_trade_type

NORMALIZATION_VERSION = 2
TYPE_FIELDS = tuple(normalize_trade_type(None))


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def listing_fields(old: Mapping[str, Any], item: Mapping[str, Any], now: datetime) -> dict:
    """Повторное наблюдение листинга не уничтожает обогащение из деталей."""
    previous = old.get("listing", {})
    changed = previous != item
    fields = dict(item)
    fields.update(listing=dict(item), last_seen_at=now, normalization_version=NORMALIZATION_VERSION)
    # При изменении типа в источнике старые детали больше не являются основанием.
    same_type = all(previous.get(k) == item.get(k) for k in (*TYPE_FIELDS, "trade_number"))
    if same_type:
        fields.update({k: old[k] for k in TYPE_FIELDS if k in old})
    if changed:
        fields.update(listing_changed_at=now, updated_at=now)
    if not old:
        fields.update(created_at=now, detail_state="pending")
    return fields


def detail_fields(old: Mapping[str, Any], detail: Mapping | None, at: datetime, now: datetime) -> dict:
    """Не принимаем ответ, запрос которого старше уже принятого ответа."""
    if not old or (old.get("detail_at") and utc(old["detail_at"]) > utc(at)):
        return {}
    fields: dict[str, Any] = {"detail_at": at, "detail_state": "not_found" if detail is None else "found"}
    if detail is not None:
        fields["detail"] = dict(detail)
        # Ответ до изменения листинга сохраняем, но не используем для новой проекции.
        fresh = not old.get("listing_changed_at") or utc(at) >= utc(old["listing_changed_at"])
        if fresh and (info := detail_type_info(detail)):
            fields.update(resolve_trade_type(info, old.get("listing", old)))
    if any(old.get(k) != v for k, v in fields.items() if k != "detail_at"):
        fields["updated_at"] = now
    fields["normalization_version"] = NORMALIZATION_VERSION
    return fields
