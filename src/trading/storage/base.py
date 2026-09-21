"""Интерфейс хранилища: то немногое, что от него нужно парсеру.

Сегодня за ним TinyDB, завтра — Mongo. Поэтому набор операций намеренно узкий
и составлен из того, что есть в обоих: upsert по ключу, счётчик, закрытие.
Ничего из специфики TinyDB (таблицы, ``Query``, файл на диске) сюда не
просачивается — иначе переезд на Mongo будет переписыванием, а не подменой.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

#: Поля, по которым документ считается тем же самым. Номер лота уникален
#: внутри площадки, но не между ними, поэтому ключ составной.
KEY_FIELDS = ("source", "lot_id")


class Store(ABC):
    """Куда складываются разобранные лоты."""

    @abstractmethod
    def upsert(self, item: Mapping[str, Any]) -> bool:
        """Записать лот, заменив прежнюю версию.

        Возвращает ``True``, если документа с таким ключом ещё не было.
        Различать вставку и обновление нужно для счётчиков запуска: сколько
        лотов появилось впервые, а сколько переписано.
        """

    @abstractmethod
    def count(self) -> int:
        """Сколько документов в хранилище."""

    @abstractmethod
    def close(self) -> None:
        """Закрыть хранилище. Повторный вызов безвреден."""

    def __enter__(self) -> Store:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
