"""Хранилище результатов парсинга.

``Store`` — интерфейс, ``MongoStore`` — реализация. Парсер про конкретную
базу не знает: решение «куда писать» принимается в одном месте.
"""

from core.db.base import KEY_FIELDS, Store, key_of
from core.db.mongo import MongoStorage

__all__ = ["KEY_FIELDS", "MongoStorage", "Store", "key_of"]
