"""Хранилище лотов в MongoDB — реализация ``Store``.

У каждой площадки своя коллекция, названная её именем (``trading.bep``,
``trading.seltim``): площадку можно пересобрать или удалить, не трогая
остальные. Поле ``source`` в документе остаётся — оно первая половина ключа,
а запрос по нескольким площадкам сводит их коллекции через ``$unionWith``.
Уникальный индекс по ``(source, lot_id)`` держит база, а не наше намерение.

Почему не файл. Прежний TinyDbStore переписывал JSON целиком на каждый upsert,
и цена записи росла вместе с числом собранных лотов: на замере 439 лотов один
upsert дорожал с 11 мс до 210 мс, а весь прогон площадки стоил 44 с чистого
CPU. Шестнадцать площадок в одном event loop делили это время между собой, и
темп обхода падал в пять раз к концу прогона при неизменном числе площадок.
У Mongo стоимость upsert не зависит от объёма собранного, а сам вызов не
блокирует loop.

Клиент можно передать снаружи (``client=``) — тогда хранилище им только
пользуется и не закрывает. Так все площадки в ``run_all`` делят один пул
соединений вместо шестнадцати своих. Без него хранилище создаёт своего через
``client.create_client`` и само его закрывает.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from bson import BSON
from pymongo.errors import DuplicateKeyError

from core.conf import conf
from core.db.base import KEY_FIELDS, Store, key_of
from core.db.mongo.client import create_client
from core.lot_state import detail_fields, listing_fields


class MongoStorage(Store):
    """Лоты одной площадки — в её коллекции.

    Экземпляр привязан к ``source``; коллекция по умолчанию называется так же.
    Запросы всё равно фильтруют по ``source``: ``collection=`` может указать и
    общую коллекцию (так делают тесты), и тогда ``count()`` считает только свои
    лоты.
    """

    def __init__(
        self,
        source: str,
        *,
        client: Any | None = None,
        uri: str | None = None,
        db_name: str | None = None,
        collection: str | None = None,
    ) -> None:
        self.source = source
        self.uri = uri or conf.mongo.uri
        self.db_name = db_name or conf.mongo.db
        self.collection_name = collection or source
        self._own_client = client is None
        self._client = client if client is not None else create_client(self.uri)

    @property
    def target(self) -> str:
        """Куда пишем — строкой для человека, в итоговый вывод парсера."""
        return f"{self.uri}/{self.db_name}.{self.collection_name} (source={self.source})"

    @property
    def collection(self) -> Any:
        if self._client is None:
            raise RuntimeError(f"Хранилище {self.target} уже закрыто")
        return self._client[self.db_name][self.collection_name]

    async def __aenter__(self) -> MongoStorage:
        # Индекс создаётся при каждом открытии: операция идемпотентная и стоит
        # один round-trip, зато уникальность ключа не зависит от того, не забыл
        # ли кто-то прогнать миграцию на новой базе.
        await self.collection.create_index([(field, 1) for field in KEY_FIELDS], unique=True)
        return self

    async def _write(self, key: dict, reduce: Callable, *, insert: bool = False) -> bool:
        """CAS: содержимое, ревизия и время записи меняются атомарно.

        При конфликте перечитываем документ и заново применяем чистое правило.
        Уникальный индекс защищает одновременно начавшиеся вставки.
        """
        for _ in range(20):
            old = await self.collection.find_one(key) or {}
            if not old and not insert:
                return False
            now = datetime.now(UTC)
            fields = reduce(old, now)
            if not fields:
                return False
            fields.update(written_at=now, revision=old.get("revision", 0) + 1)
            if not old:
                try:
                    await self.collection.insert_one({**key, **fields})
                    return True
                except DuplicateKeyError:
                    continue
            guard = {**key, "revision": old.get("revision", {"$exists": False})}
            result = await self.collection.update_one(guard, {"$set": fields})
            if result.matched_count:
                return False
        raise RuntimeError(f"Concurrent update retry limit for {key}")

    async def upsert(self, item: Mapping[str, Any]) -> bool:
        """Сохранить наблюдение листинга вместе с метками времени."""
        key = key_of(item)
        # Сравниваем значения в точности хранения Mongo (UTC, миллисекунды).
        observed = BSON.encode(dict(item)).decode()
        return await self._write(key, lambda old, now: listing_fields(old, observed, now), insert=True)

    def pending_detail(
        self, limit: int = 0, statuses: list[str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Лоты, которым нужна страница деталей: новые или изменившиеся.

        Отдельного состояния («время последнего прогона») нет — оно в самих
        документах. Деталей ещё нет (нет ``detail_at``) — лот новый; лот
        изменился после них (``listing_changed_at > detail_at``) — детали устарели.
        Лот, чья страница не открылась, ``detail_at`` не получит и попадёт в
        выборку снова. Свежие — первыми. ``statuses`` — только лоты с этими
        статусами (как их пишет листинг).
        """
        query: dict[str, Any] = {
            "source": self.source,
            "$or": [
                {"detail_at": {"$exists": False}},
                {"$expr": {"$gt": [{"$ifNull": ["$listing_changed_at", "$updated_at"]}, "$detail_at"]}},
            ],
        }
        if statuses:
            query["status"] = {"$in": statuses}
        # trade_url — адрес страницы торгов: у kendo, btorg и rus-on детали
        # берутся с неё. У лотов iTender поля нет — в выдаче его просто не будет.
        projection = {"_id": 0, "lot_id": 1, "lot_url": 1, "trade_url": 1}
        return self.collection.find(query, projection).sort("created_at", -1).limit(limit)

    async def save_detail(self, lot_id: str, detail: Mapping[str, Any] | None, at: datetime) -> None:
        """Сохранить детали; at — нижняя граница времени запроса, не время записи."""
        key = {"source": self.source, "lot_id": lot_id}
        await self._write(key, lambda old, now: detail_fields(old, detail, at, now))

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
