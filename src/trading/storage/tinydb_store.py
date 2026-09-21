"""Реализация ``Store`` поверх TinyDB — один JSON-файл на площадку.

TinyDB выбран как промежуточная ступень к Mongo: документная модель та же,
так что структура айтема при переезде не поменяется, — а инфраструктуры пока
никакой не нужно. Цена — всё в памяти и запись файла целиком на каждый upsert;
на десятках тысяч лотов это станет узким местом, и вот тогда придёт Mongo.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from tinydb import Query, TinyDB

from trading.storage.base import KEY_FIELDS, Store


class TinyDbStore(Store):
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # ensure_ascii=False — иначе файл станет нечитаемым частоколом \uXXXX:
        # здесь всё содержимое кириллическое. Вместе с ним обязателен
        # encoding="utf-8": TinyDB открывает файл в кодировке системы, а на
        # Windows это cp1251, и файл получается не-UTF-8 — JSON, который
        # больше никто не прочитает.
        self._db: TinyDB | None = TinyDB(self.path, encoding="utf-8", ensure_ascii=False, indent=2)

    @property
    def db(self) -> TinyDB:
        if self._db is None:
            raise RuntimeError(f"Хранилище {self.path} уже закрыто")
        return self._db

    def upsert(self, item: Mapping[str, Any]) -> bool:
        missing = [field for field in KEY_FIELDS if not item.get(field)]
        if missing:
            # Без ключа документ нельзя ни найти, ни обновить — он просто
            # копился бы дублями при каждом запуске.
            raise ValueError(f"В айтеме нет ключевых полей {missing}: {_preview(item)}")

        query = Query().fragment({field: item[field] for field in KEY_FIELDS})
        is_new = not self.db.contains(query)
        self.db.upsert(dict(item), query)
        return is_new

    def count(self) -> int:
        return len(self.db)

    def close(self) -> None:
        if self._db is not None:
            self._db.close()
            self._db = None


def _preview(item: Mapping[str, Any]) -> str:
    """Короткая выжимка айтема для текста ошибки — не весь документ в лог."""
    return json.dumps({k: item.get(k) for k in list(item)[:4]}, ensure_ascii=False)[:120]
