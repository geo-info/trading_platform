"""Хранилище результатов парсинга.

``Store`` — интерфейс, ``TinyDbStore`` — сегодняшняя реализация. Парсеры про
хранилище не знают: решение «куда писать» принимается в одном месте, а не
размазано по файлам площадок.
"""

from trading.storage.base import Store
from trading.storage.tinydb_store import TinyDbStore

__all__ = ["Store", "TinyDbStore"]
