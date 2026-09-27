"""Разбор значений, общий для площадок: цена, дата, статус.

Перенесено из coll-temp (``collector/core/parsing.py``): при неудаче функции
молча возвращают ``None`` — лот не должен падать из-за одной кривой ячейки.
Отличия от оригинала: даты получают московский пояс, статус сводится к одному
написанию.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from zoneinfo import ZoneInfo

logger = logging.getLogger(__name__)

#: Часовой пояс площадок. На Windows база поясов приходит пакетом tzdata.
MSK = ZoneInfo("Europe/Moscow")

# Ведущая числовая часть: пробелы/nbsp как разделители тысяч, точка или запятая
# как десятичная. Останавливается перед хвостом «руб, НДС не облагается».
_PRICE_HEAD_RE = re.compile(r"[\d\s\xa0.,]+")
# ДД.ММ.ГГГГ с необязательным ЧЧ:ММ[:СС]; хвост вроде «(33 дн.)» игнорируется.
_DATETIME_RE = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})(?:\D+(\d{2}):(\d{2})(?::(\d{2}))?)?")

# Статусы, означающие, что торги закончены. Всё остальное, включая незнакомый
# или пустой статус, считается живым — обход не обрезается на сомнении.
_FINISHED_MARKERS = (
    "завершен",
    "завершён",
    "состоял",
    "отменен",
    "отменён",
    "приостановлен",
    "аннулирован",
    "признан",
    "окончен",
)


def clean(value: str | None) -> str | None:
    """Схлопнуть пробелы и неразрывные пробелы; пустая строка — это ``None``."""
    if value is None:
        return None
    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip() or None


def is_active_status(status: str | None) -> bool:
    """Идут ли ещё торги. Незнакомый или пустой статус — идут."""
    if not status:
        return True
    lowered = status.lower()
    return not any(marker in lowered for marker in _FINISHED_MARKERS)


def parse_price(value: str | None) -> float | None:
    """Сумма в рублях: «270 000,00», «1 315 000.00», «280 000,00 руб, НДС…»."""
    if value is None:
        return None
    m = _PRICE_HEAD_RE.match(value)
    if not m:
        return None
    raw = m.group(0).replace("\xa0", "").replace(" ", "").replace(",", ".").strip().rstrip(".")
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        logger.warning("parsing.bad_price value=%s", value)
        return None


def parse_datetime(value: str | None) -> datetime | None:
    """«ДД.ММ.ГГГГ[ ЧЧ:ММ[:СС]]» -> datetime по Москве, иначе ``None``.

    Площадки пишут московское время, не говоря об этом. Наивный datetime
    драйвер Mongo сохранил бы как UTC, и в любом инструменте, читающем BSON
    Date честно, торги сдвинулись бы на три часа.
    """
    if not value:
        return None
    m = _DATETIME_RE.search(value)
    if not m:
        return None
    day, month, year, hour, minute, second = m.groups()
    try:
        return datetime(
            int(year), int(month), int(day), int(hour or 0), int(minute or 0), int(second or 0), tzinfo=MSK
        )
    except ValueError:
        return None


#: Написания одного статуса на разных площадках -> одно. tendergarant и utender
#: пишут «Приём», остальные «Прием»; без сведения группировка по статусу врёт.
STATUS_SYNONYMS = {
    "Прием заявок": "Приём заявок",
    "Прием заявок на интервале не активен": "Приём заявок на интервале не активен",
}


def normalize_status(status: str | None) -> str | None:
    return STATUS_SYNONYMS.get(status, status) if status else status
