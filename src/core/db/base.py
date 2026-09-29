"""Интерфейс хранилища: то немногое, что от него нужно парсеру.

Набор операций намеренно узкий — upsert по ключу, счётчик, закрытие. Ничего
из специфики драйвера (коллекции, индексы, фильтры) сюда не просачивается:
парсер не должен знать, во что он пишет.

Методы асинхронные, потому что асинхронен сам обход. Синхронная запись в
общем event loop блокирует не только свою площадку, но и все остальные,
которые идут рядом, — на этом и горел прежний файловый вариант.
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Mapping
from datetime import datetime
from typing import Any

#: Поля, по которым документ считается тем же самым. Номер лота уникален
#: внутри площадки, но не между ними, поэтому ключ составной.
KEY_FIELDS = ("source", "lot_id")


class Store(ABC):
    """Куда складываются разобранные лоты."""

    @property
    def target(self) -> str:
        """Куда пишем — строкой для человека, в лог прогона."""
        return type(self).__name__

    @abstractmethod
    async def upsert(self, item: Mapping[str, Any]) -> bool:
        """Записать лот, обновив прежнюю версию.

        Возвращает ``True``, если документа с таким ключом ещё не было.
        Различать вставку и обновление нужно для счётчиков запуска: сколько
        лотов появилось впервые, а сколько переписано.
        """

    @abstractmethod
    def pending_detail(
        self, limit: int = 0, statuses: list[str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """``lot_id``, ``lot_url`` и ``trade_url`` (если есть) лотов, которым нужна страница деталей;
        ``statuses`` — только с этими статусами."""

    @abstractmethod
    async def save_detail(self, lot_id: str, detail: Mapping[str, Any], at: datetime) -> None:
        """Дописать детали к лоту; ``at`` — когда страница была запрошена."""

    @abstractmethod
    async def count(self) -> int:
        """Сколько документов этой площадки в хранилище."""

    @abstractmethod
    async def close(self) -> None:
        """Закрыть хранилище. Повторный вызов безвреден."""

    async def __aenter__(self) -> Store:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()


def key_of(item: Mapping[str, Any]) -> dict[str, Any]:
    """Ключ документа. Пустое или отсутствующее поле — ошибка, а не ключ.

    Без ключа документ нельзя ни найти, ни обновить: он копился бы дублями
    при каждом запуске, и заметили бы это сильно позже.
    """
    missing = [field for field in KEY_FIELDS if not item.get(field)]
    if missing:
        raise ValueError(f"В айтеме нет ключевых полей {missing}: {preview(item)}")
    return {field: item[field] for field in KEY_FIELDS}


def preview(item: Mapping[str, Any]) -> str:
    """Короткая выжимка айтема для текста ошибки — не весь документ в лог."""
    return json.dumps({k: item.get(k) for k in list(item)[:4]}, ensure_ascii=False)[:120]
