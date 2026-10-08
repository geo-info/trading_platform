"""Тип торгов: явный текст приоритетнее кода; неизвестные коды не угадываем."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from core.help import clean

# Подтверждены полными названиями на страницах Kendo и rus-on.
CODES = {
    "ОАОФ": "Открытый аукцион с открытой формой представления цены",
    "ОАЗФ": "Открытый аукцион с закрытой формой представления цены",
    "ЗАОФ": "Закрытый аукцион с открытой формой представления цены",
    "ЗАЗФ": "Закрытый аукцион с закрытой формой представления цены",
    "ОКОФ": "Открытый конкурс с открытой формой представления цены",
    "ОКЗФ": "Открытый конкурс с закрытой формой представления цены",
    "ЗКОФ": "Закрытый конкурс с открытой формой представления цены",
    "ЗКЗФ": "Закрытый конкурс с закрытой формой представления цены",
    "ОТПП": "Открытые торги посредством публичного предложения",
    "ЗТПП": "Закрытые торги посредством публичного предложения",
}
TYPE_LABELS = ("Тип торгов", "Вид торгов", "Форма торгов", "Форма проведения торгов и подачи предложений")
ATTRIBUTE_LABELS = {
    "Форма торга по составу участников": "trade_participation",
    "Форма представления предложений о цене": "trade_price_form",
}


def number_type(number: str | None) -> str | None:
    """Весь суффикс номера, включая неизвестные модификаторы и пояснение."""
    match = re.match(r"^\s*\d+\s*[-–—]\s*(.+)$", number or "")
    return clean(match[1]) if match else None


def normalize_trade_type(raw: str | None, *, source: str | None = None) -> dict[str, Any]:
    raw = clean(raw)
    code_match = re.fullmatch(r"([А-ЯЁA-Z]{2,}(?:[-–—][А-ЯЁA-Z]+)*)(?:\s*\((.+)\))?", raw or "")
    code = code_match[1] if code_match else None
    text = clean(code_match[2]) if code_match else raw
    if not text and code:
        # -К и другие модификаторы сохраняем, но их смысл не выводим.
        text = CODES.get(re.split("[-–—]", code)[0])
    lowered = (text or "").lower().replace("ё", "е")
    kind = (
        "публичное предложение"
        if re.search(r"публичн\w*\s+предложени", lowered)
        else next((value for value in ("аукцион", "конкурс") if value in lowered), None)
    )
    participation = None
    if re.search(r"закрыт\w*\s+(?:аукцион|конкурс|торги|публичное предложение)", lowered):
        participation = "закрытая"
    elif re.search(r"открыт\w*\s+(?:аукцион|конкурс|торги|публичное предложение)", lowered):
        participation = "открытая"
    price_form = None
    if re.search(r"открыт\w*\s+форм", lowered):
        price_form = "открытая"
    elif re.search(r"закрыт\w*\s+форм", lowered):
        price_form = "закрытая"
    return {
        "trade_type": text or raw,
        "trade_type_raw": raw,
        "trade_type_code": code,
        "trade_type_source": source if raw else None,
        "trade_kind": kind,
        "trade_participation": participation,
        "trade_price_form": price_form,
        "trade_type_conflicts": [],
    }


def resolve_trade_type(info: Mapping[str, Any], trade: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Явная подпись, пояснение номера страницы, затем сведения листинга."""
    trade = trade or {}
    for label in TYPE_LABELS:
        if isinstance(info.get(label), str) and clean(info[label]):
            result = normalize_trade_type(info[label], source=f"page:{label}")
            fallback = normalize_trade_type(
                number_type(info.get("Номер торгов") or trade.get("trade_number"))
                or trade.get("trade_type_raw")
                or trade.get("trade_type")
            )
            result["trade_type_code"] = result["trade_type_code"] or fallback["trade_type_code"]
            return explicit_attributes(result, info)
    raw = number_type(info.get("Номер торгов"))
    if raw:
        number = normalize_trade_type(raw, source="page:Номер торгов")
        stored_raw = trade.get("trade_type_raw") or trade.get("trade_type")
        stored = normalize_trade_type(stored_raw, source=trade.get("trade_type_source") or "listing")
        if (
            number["trade_type_raw"] == number["trade_type_code"]
            and stored_raw
            and stored_raw != stored["trade_type_code"]
        ):
            # Голый код страницы не вытесняет уже полученное явное название.
            stored["trade_type_code"] = number["trade_type_code"] or trade.get("trade_type_code")
            return explicit_attributes(stored, info)
        return explicit_attributes(number, info)
    raw = trade.get("trade_type_raw") or trade.get("trade_type") or number_type(trade.get("trade_number"))
    result = normalize_trade_type(raw, source=trade.get("trade_type_source") or "listing")
    result["trade_type_code"] = result["trade_type_code"] or trade.get("trade_type_code")
    return explicit_attributes(result, info)


def explicit_attributes(result: dict[str, Any], info: Mapping[str, Any]) -> dict[str, Any]:
    for label, key in ATTRIBUTE_LABELS.items():
        value = clean(info.get(label))
        if value and value.lower() in ("открытая", "закрытая"):
            if result.get(key) and result[key] != value.lower():
                result["trade_type_conflicts"].append(
                    {
                        "field": key,
                        "from_type": result[key],
                        "explicit": value.lower(),
                        "source": f"page:{label}",
                    }
                )
            result[key] = value.lower()
    return result


def detail_type_info(detail: Mapping[str, Any]) -> dict[str, str]:
    """Только подписанные поля, в том числе разделы iTender; без поиска в описании."""
    info = {}
    for label, value in detail.items():
        if label in (*TYPE_LABELS, *ATTRIBUTE_LABELS, "Номер торгов") and isinstance(value, str):
            info[label] = value
        elif isinstance(value, Mapping):
            info.update(detail_type_info(value))
    return info
