"""Мини-подделка коллекции Mongo — ровно те три операции, что нужны ``MongoStore``.

Настоящей базы в тестах нет: поднимать mongod ради проверки того, что мы
правильно собираем фильтр и правильно читаем ответ драйвера, — дорого и
хрупко. Подделка повторяет контракт ``update_one``/``count_documents``
настолько, насколько он нам важен: ключ, слияние через ``$set``, ``$setOnInsert`` только при вставке и признак
вставки в ``upserted_id``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class FakeResult:
    upserted_id: Any | None


@dataclass
class FakeCollection:
    docs: dict[tuple, dict] = field(default_factory=dict)
    indexes: list[tuple] = field(default_factory=list)

    async def create_index(self, keys: list[tuple[str, int]], unique: bool = False) -> str:
        self.indexes.append((tuple(keys), unique))
        return "idx"

    async def update_one(self, filt: dict, update: dict, upsert: bool = False) -> FakeResult:
        key = tuple(sorted(filt.items()))
        existed = key in self.docs
        if not existed and not upsert:
            return FakeResult(None)
        doc = self.docs.setdefault(key, {})
        if not existed:
            doc.update(update.get("$setOnInsert", {}))
        doc.update(update["$set"])
        return FakeResult(None if existed else f"oid-{len(self.docs)}")

    async def count_documents(self, filt: dict) -> int:
        return sum(1 for doc in self.docs.values() if all(doc.get(f) == v for f, v in filt.items()))


@dataclass
class FakeDb:
    collections: dict[str, FakeCollection] = field(default_factory=dict)

    def __getitem__(self, name: str) -> FakeCollection:
        return self.collections.setdefault(name, FakeCollection())


@dataclass
class FakeClient:
    dbs: dict[str, FakeDb] = field(default_factory=dict)
    closed: bool = False

    def __getitem__(self, name: str) -> FakeDb:
        return self.dbs.setdefault(name, FakeDb())

    async def close(self) -> None:
        self.closed = True
