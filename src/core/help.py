"""Мелкие помощники разбора, общие для парсеров.

Разбор значений (цена, дата) при неудаче молча возвращает ``None``: лот не
должен падать из-за одной кривой ячейки, сырая строка всё равно остаётся в
документе.
"""

from __future__ import annotations

import re
from datetime import datetime
from itertools import takewhile
from zoneinfo import ZoneInfo

#: Часовой пояс площадок. На Windows база поясов приходит пакетом tzdata.
MSK = ZoneInfo("Europe/Moscow")

#: Ведущая числовая часть: пробелы как разделители тысяч, точка или запятая
#: как десятичная. Останавливается перед хвостом «руб, НДС не облагается».
_PRICE_HEAD_RE = re.compile(r"[\d\s.,]+")
#: ДД.ММ.ГГГГ с необязательным ЧЧ:ММ[:СС]; хвост вроде «(33 дн.)» не мешает.
_DATETIME_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\D+(\d{2}):(\d{2})(?::(\d{2}))?)?")


def clean(value: str | None) -> str | None:
    """Схлопнуть пробелы и неразрывные пробелы; пустая строка — это ``None``."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip() or None


def digits(text: str | None) -> str:
    """Ведущие цифры строки: «10840–ОАОФ» -> «10840»."""
    return "".join(takewhile(str.isdigit, text or ""))


def parse_price(value: str | None) -> float | None:
    """Сумма в рублях: «270 000,00», «1 315 000.00», «280 000,00 руб, НДС…»."""
    m = _PRICE_HEAD_RE.match(clean(value) or "")
    if not m:
        return None
    raw = m.group(0).replace(" ", "").replace(",", ".").rstrip(".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_datetime(value: str | None) -> datetime | None:
    """«ДД.ММ.ГГГГ[ ЧЧ:ММ[:СС]]» -> datetime по Москве, иначе ``None``.

    Площадки пишут московское время, не говоря об этом. Наивный datetime
    драйвер Mongo сохранил бы как UTC, и торги сдвинулись бы на три часа.
    """
    m = _DATETIME_RE.search(value or "")
    if not m:
        return None
    day, month, year, hour, minute, second = m.groups()
    try:
        return datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0), tzinfo=MSK
        )
    except ValueError:
        return None
