"""Реализация ``Store`` поверх MongoDB.

Все площадки пишут в одну коллекцию, а не в отдельные: документ у них общий,
а разделяет их поле ``source``, оно же первая половина ключа. Так запрос
«покажи лот по номеру ЕФРСБ» или «все лоты дороже миллиона» пишется один раз,
а не шестнадцать. Уникальный индекс по ``(source, lot_id)`` — тот же ключ,
что и раньше, только теперь его держит база, а не наше намерение.

Почему не файл. Прежний TinyDbStore переписывал JSON целиком на каждый upsert,
и цена записи росла вместе с числом собранных лотов: на замере 439 лотов один
upsert дорожал с 11 мс до 210 мс, а весь прогон площадки стоил 44 с чистого
CPU. Шестнадцать площадок в одном event loop делили это время между собой, и
темп обхода падал в пять раз к концу прогона при неизменном числе площадок.
У Mongo стоимость upsert не зависит от объёма собранного, а сам вызов не
блокирует loop.

Клиент можно передать снаружи (``client=``) — тогда хранилище им только
пользуется и не закрывает. Так все площадки в ``run_all`` делят один пул
соединений вместо шестнадцати своих.
"""

from __future__ import annotations

import os
from collections.abc import Mapping
from typing import Any

from pymongo import AsyncMongoClient

from trading.storage.base import KEY_FIELDS, Store, key_of

DEFAULT_URI = "mongodb://localhost:27017"
DEFAULT_DB = "trading"
DEFAULT_COLLECTION = "lots"


def mongo_uri() -> str:
    """Адрес Mongo: переменная окружения или локальная база по умолчанию."""
    return os.getenv("MONGO_URI", DEFAULT_URI)


def mongo_db_name() -> str:
    return os.getenv("MONGO_DB", DEFAULT_DB)


class MongoStore(Store):
    """Лоты одной площадки в общей коллекции.

    Экземпляр привязан к ``source``: ``count()`` считает только свои лоты, а
    не всю коллекцию, — иначе счётчик в конце прогона площадки ничего бы не
    говорил именно о ней.
    """

    def __init__(
        self,
        source: str,
        *,
        client: Any | None = None,
        uri: str | None = None,
        db_name: str | None = None,
        collection: str = DEFAULT_COLLECTION,
    ) -> None:
        self.source = source
        self.uri = uri or mongo_uri()
        self.db_name = db_name or mongo_db_name()
        self.collection_name = collection
        # Свой клиент закрываем, чужой — нет: его одолжили, и закрыть его
        # значит оборвать соседние площадки на середине обхода.
        self._own_client = client is None
        self._client = client if client is not None else AsyncMongoClient(self.uri)

    @property
    def target(self) -> str:
        """Куда пишем — строкой для человека, в итоговый вывод парсера."""
        return f"{self.uri}/{self.db_name}.{self.collection_name} (source={self.source})"

    @property
    def collection(self) -> Any:
        if self._client is None:
            raise RuntimeError(f"Хранилище {self.target} уже закрыто")
        return self._client[self.db_name][self.collection_name]

    async def __aenter__(self) -> MongoStore:
        # Индекс создаётся при каждом открытии: операция идемпотентная и стоит
        # один round-trip, зато уникальность ключа не зависит от того, не забыл
        # ли кто-то прогнать миграцию на новой базе.
        await self.collection.create_index([(field, 1) for field in KEY_FIELDS], unique=True)
        return self

    async def upsert(self, item: Mapping[str, Any]) -> bool:
        result = await self.collection.update_one(key_of(item), {"$set": dict(item)}, upsert=True)
        return result.upserted_id is not None

    async def count(self) -> int:
        return await self.collection.count_documents({"source": self.source})

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and self._own_client:
            await client.close()
