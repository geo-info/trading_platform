"""Хранилище результатов парсинга.

``Store`` — интерфейс, ``MongoStore`` — сегодняшняя реализация. Парсеры про
хранилище не знают: решение «куда писать» принимается в одном месте, а не
размазано по файлам площадок.
"""

from trading.storage.base import KEY_FIELDS, Store, key_of
from trading.storage.mongo_store import DEFAULT_COLLECTION, DEFAULT_DB, DEFAULT_URI, MongoStore, mongo_uri

__all__ = [
    "DEFAULT_COLLECTION",
    "DEFAULT_DB",
    "DEFAULT_URI",
    "KEY_FIELDS",
    "MongoStore",
    "Store",
    "key_of",
    "mongo_uri",
]
