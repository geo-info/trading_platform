"""Подключение к MongoDB — одно место, где создаётся клиент.

Клиент ``AsyncMongoClient`` держит внутри пул соединений и фоновые задачи
мониторинга сервера. Создавать его где попало значит получить по пулу на
каждое место: раньше клиент заводили и ``run_all`` (один на все площадки), и
``MongoStore`` (свой, если чужой не передали). Здесь решается, куда и как
подключаться; остальные берут клиента отсюда.

Соединение открывается лениво, на первом запросе, так что создать клиента
дёшево и без сети.
"""

from __future__ import annotations

from pymongo import AsyncMongoClient

from core.conf import conf


def create_client(uri: str | None = None) -> AsyncMongoClient:
    """Клиент Mongo по адресу ``uri``, по умолчанию — из настроек.

    Закрывает клиента тот, кто его создал: ``await client.close()``.
    """
    return AsyncMongoClient(uri or conf.mongo.uri)
