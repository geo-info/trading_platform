"""Хранилище лотов в MongoDB — реализация ``Store``.

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
соединений вместо шестнадцати своих. Без него хранилище создаёт своего через
``client.create_client`` и само его закрывает.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from core.conf import conf
from core.db.base import KEY_FIELDS, Store, key_of
from core.db.mongo.client import create_client


class MongoStorage(Store):
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
    ) -> None:
        self.source = source
        self.uri = uri or conf.mongo.uri
        self.db_name = db_name or conf.mongo.db
        self.collection_name = collection or conf.mongo.collection
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

    async def upsert(self, item: Mapping[str, Any]) -> bool:
        """Записать лот; ``updated_at`` сдвигается, только если лот изменился.

        ``created_at`` и ``updated_at`` ставятся при вставке. При повторном
        обходе ``$set`` с теми же значениями Mongo считает пустым обновлением
        (``modified_count == 0``), и ``updated_at`` остаётся прежним: по нему
        видно, когда на площадке последний раз что-то поменялось — обычно статус.
        Поэтому в айтеме не должно быть полей, меняющихся на каждом обходе
        (время загрузки и т. п.), — иначе лот «меняется» всегда.
        """
        now = datetime.now(UTC)
        key = key_of(item)
        update = {"$set": dict(item), "$setOnInsert": {"created_at": now, "updated_at": now}}
        result = await self.collection.update_one(key, update, upsert=True)
        if result.modified_count:
            await self.collection.update_one(key, {"$set": {"updated_at": now}})
        return result.upserted_id is not None

    def pending_detail(
        self, limit: int = 0, statuses: list[str] | None = None
    ) -> AsyncIterator[dict[str, Any]]:
        """Лоты, которым нужна страница деталей: новые или изменившиеся.

        Отдельного состояния («время последнего прогона») нет — оно в самих
        документах. Деталей ещё нет (нет ``detail_at``) — лот новый; лот
        изменился после них (``updated_at > detail_at``) — детали устарели.
        Лот, чья страница не открылась, ``detail_at`` не получит и попадёт в
        выборку снова. Свежие — первыми. ``statuses`` — только лоты с этими
        статусами (как их пишет листинг).
        """
        query: dict[str, Any] = {
            "source": self.source,
            "$or": [
                {"detail_at": {"$exists": False}},
                {"$expr": {"$gt": ["$updated_at", "$detail_at"]}},
            ],
        }
        if statuses:
            query["status"] = {"$in": statuses}
        # trade_url — адрес страницы торгов: у kendo, btorg и rus-on детали
        # берутся с неё. У лотов iTender поля нет — в выдаче его просто не будет.
        projection = {"_id": 0, "lot_id": 1, "lot_url": 1, "trade_url": 1}
        return self.collection.find(query, projection).sort("created_at", -1).limit(limit)

    async def save_detail(self, lot_id: str, detail: Mapping[str, Any] | None, at: datetime) -> None:
        """Дописать детали к лоту.

        ``at`` — когда страница была *запрошена*, а не записана: если листинг
        обновил лот, пока шёл запрос, его ``updated_at`` окажется позже, и лот
        перечитается. ``updated_at`` не трогаем — он значит «лот изменился на
        площадке», а не «мы дописали детали».

        ``detail=None`` — страница торгов открылась, но лота на ней нет (снят
        с торгов). Ставится только ``detail_at``: иначе лот стоял бы в
        ``pending_detail`` вечно и перечитывался каждый прогон. Прежние детали
        остаются; изменится лот в листинге — детали запросятся снова.
        """
        key = {"source": self.source, "lot_id": lot_id}
        fields: dict[str, Any] = {"detail_at": at}
        if detail is not None:
            fields["detail"] = dict(detail)
        await self.collection.update_one(key, {"$set": fields})

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
