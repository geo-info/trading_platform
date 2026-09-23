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

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from pymongo import AsyncMongoClient

from core.db.base import KEY_FIELDS, Store, key_of
from core.settings import settings


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
        collection: str | None = None,
        run_id: str | None = None,
    ) -> None:
        self.source = source
        #: Метка запуска. ``run_all`` передаёт одну на все площадки, чтобы
        #: «что видел последний обход» было одним запросом по run_id.
        self.run_id = run_id or new_run_id()
        self.uri = uri or settings.mongo_uri
        self.db_name = db_name or settings.mongo_db
        self.collection_name = collection or settings.mongo_collection
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
        """Записать лот, отметив, когда его видели впервые и в последний раз.

        ``$set`` перезаписывает всё, что пришло с площадки, и без отдельных
        отметок лот, который площадка давно убрала, не отличить от живого: у
        обоих одинаково свежий вид. ``first_seen_at`` пишется только при
        вставке (``$setOnInsert``), ``last_seen_at`` и ``run_id`` — каждый раз.
        Лот, чей ``run_id`` отстал от последнего запуска, этим запуском не увиден.
        """
        now = datetime.now(UTC)
        update = {
            "$set": {**item, "last_seen_at": now, "run_id": self.run_id},
            "$setOnInsert": {"first_seen_at": now},
        }
        result = await self.collection.update_one(key_of(item), update, upsert=True)
        return result.upserted_id is not None

    async def count(self) -> int:
        return await self.collection.count_documents({"source": self.source})

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and self._own_client:
            await client.close()


def new_run_id() -> str:
    """Метка запуска: время старта для глаз и хвост, чтобы два запуска в одну
    секунду не слились."""
    return f"{datetime.now(UTC):%Y%m%dT%H%M%SZ}-{uuid4().hex[:6]}"
