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
from collections.abc import Mapping
from typing import Any

#: Поля, по которым документ считается тем же самым. Номер лота уникален
#: внутри площадки, но не между ними, поэтому ключ составной.
KEY_FIELDS = ("source", "lot_id")


class Store(ABC):
    """Куда складываются разобранные лоты."""

    @abstractmethod
    async def upsert(self, item: Mapping[str, Any]) -> bool:
        """Записать лот, обновив прежнюю версию.

        Возвращает ``True``, если документа с таким ключом ещё не было.
        Различать вставку и обновление нужно для счётчиков запуска: сколько
        лотов появилось впервые, а сколько переписано.
        """

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
