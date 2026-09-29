"""Зависимость прогона: хранилище и обход одним контекстным менеджером.

Как ``Depends`` в FastAPI: зависимость — функция с ``yield``. До ``yield`` —
открыть ресурсы, после — закрыть. Парсер получает готовый прогон и не знает,
как он собран; подменить его (в тесте, для другой коллекции или логов) —
значит передать другую функцию.

    async with open_run(Alfalot, params={"max_pages": 30}) as run:
        async for item in run.crawl.stream():
            await run.storage.upsert(item)
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from collector import Crawl, Crawler, open_crawl

from core.db.base import Store
from core.db.mongo.storage import MongoStorage

logger = logging.getLogger("tp")


@dataclass
class Run:
    """Открытый прогон площадки: куда писать и что обходить."""

    storage: Store
    crawl: Crawl

    @property
    def log(self) -> Callable[[str], Awaitable[None]]:
        """Лог прогона — тот же, что у парсера, с меткой площадки."""
        return self.crawl.crawler.log


#: По классу парсера — открытый прогон.
RunDep = Callable[..., AbstractAsyncContextManager[Run]]


@asynccontextmanager
async def open_run(
    crawler: type[Crawler],
    *,
    params: Mapping[str, Any] | None = None,
    collection: str | None = None,
) -> AsyncIterator[Run]:
    """Прогон площадки ``crawler``: её хранилище и обход.

    ``params`` — параметры прогона для фреймворка (``max_pages``, ``limit``);
    ``collection`` — куда писать, по умолчанию общая коллекция из настроек.
    """

    async def log(message: str) -> None:
        logger.info("[%s] %s", crawler.name, message)

    async with (
        MongoStorage(source=crawler.name, collection=crawler.name) as storage,
        # Хранилище — и парсеру (ctx.sink): детальный берёт из него, какие лоты обходить.
        open_crawl(crawler, params=params, sink=storage, log=log) as crawl,
    ):
        yield Run(storage, crawl)
