"""Lot — лот листинга, один на все движки и площадки.

Поля названы так, как их отдаёт строка листинга iTender, — у остальных движков
то же самое называется так же. Значения — как на площадке, строками: так
документ можно сверить со страницей глазами. Рядом — разобранные значения
(``price_value``, ``bids_end_at``, ``auction_at``, ``is_active``): их модель
считает сама, в документ они попадают через ``model_dump()``.

Детали лота (страница лота) — не здесь: их дописывает детальный парсер
отдельным полем ``detail`` (``Store.save_detail``), у каждого движка своего
вида. Модель описывает то, что кладёт в базу листинг.

Незнакомые поля запрещены: опечатка в имени поля у парсера всплывает сразу, а
не копится в базе вторым написанием того же.

    item = Lot(source="bep", lot_id="1", lot_url="https://…", price="135 000.00").model_dump()
    await storage.upsert(item)
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, computed_field

from core.help import parse_datetime, parse_price

#: Части статусов, означающих, что торги закончены. Всё остальное, включая
#: незнакомый или пустой статус, считается живым: лот не теряется на сомнении.
FINISHED_MARKERS = (
    "заверш",
    "состоял",
    "отмен",
    "приостановлен",
    "аннулирован",
    "признан",
    "окончен",
)


def is_active_status(status: str | None) -> bool:
    """Идут ли ещё торги. Незнакомый или пустой статус — идут."""
    lowered = (status or "").lower().replace("ё", "е")
    return not any(marker in lowered for marker in FINISHED_MARKERS)


class Lot(BaseModel):
    """Один лот торгов, как его видит листинг."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    #: Площадка — ``name`` краулера; вместе с ``lot_id`` — ключ документа.
    source: str
    #: Номер лота, уникальный внутри площадки.
    lot_id: str
    #: Страница лота для человека. Если своей страницы у лота нет — страница торгов.
    lot_url: str
    #: Откуда детальный парсер берёт детали лота, если не со страницы лота:
    #: страница торгов или фрагмент с лотами. Лоты одних торгов делят один адрес.
    trade_url: str | None = None

    trade_id: str | None = None
    #: Номер торгов, как его пишет площадка: «10840–ОАОФ».
    trade_number: str | None = None
    trade_type: str | None = None
    auction_name: str | None = None
    lot_num: str | None = None
    description: str | None = None

    organizer: str | None = None
    debtor: str | None = None
    winner: str | None = None

    #: Начальная цена, как на площадке.
    price: str | None = None
    #: Окончание приёма заявок, как на площадке.
    bids_end: str | None = None
    #: Дата торгов (подведения результатов), как на площадке.
    auction_date: str | None = None
    status: str | None = None

    @computed_field
    @property
    def price_value(self) -> float | None:
        return parse_price(self.price)

    @computed_field
    @property
    def bids_end_at(self) -> datetime | None:
        return parse_datetime(self.bids_end)

    @computed_field
    @property
    def auction_at(self) -> datetime | None:
        return parse_datetime(self.auction_date)

    @computed_field
    @property
    def is_active(self) -> bool:
        return is_active_status(self.status)
