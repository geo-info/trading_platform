"""Общее для тестов: фикстуры-страницы, офлайн-ответы краулеру, хранилище на Mongo.

Краулер в тестах не ходит в сеть: колбэки (``parse``, ``parse_trade``,
``start_requests``) вызываются напрямую, а ответом служит HTML-фикстура,
завёрнутая в ``Response`` фреймворка. Так проверяется и разбор, и то, какие
запросы краулер отдаёт дальше.
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterable, AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from collector import Crawler, CrawlerContext, Request, Response
from parsel import Selector
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

from core.db.mongo.storage import MongoStorage

TESTS = Path(__file__).parent


def read_fixture(path: str, encoding: str = "utf-8") -> str:
    """Текст фикстуры по пути от ``tests/``: ``read_fixture("kendo/fixtures/trade_10840.html")``."""
    return (TESTS / path).read_text(encoding=encoding)


def page(path: str, encoding: str = "utf-8") -> Selector:
    return Selector(read_fixture(path, encoding))


def make(crawler_cls: type[Crawler], *, params: dict[str, Any] | None = None, sink: Any = None) -> Crawler:
    """Краулер без HTTP: для прямого вызова колбэков."""
    return crawler_cls(CrawlerContext(http=None, params=params or {}, sink=sink))


def respond(crawler: Crawler, request: Request, text: str, status: int = 200) -> Response:
    """Ответ на ``request`` с телом ``text`` — как будто его вернул сервер."""
    return Response(SimpleNamespace(status_code=status, text=text, headers={}), request, crawler)


async def collect(agen: AsyncIterable[Any]) -> tuple[list[Request], list[Any]]:
    """Всё, что отдал колбэк: запросы и айтемы отдельно."""
    out = [x async for x in agen]
    return [x for x in out if isinstance(x, Request)], [x for x in out if not isinstance(x, Request)]


class Sink:
    """Хранилище-заглушка для детального парсера: отдаёт заданные лоты как ``pending_detail``."""

    def __init__(self, lots: list[dict[str, Any]]) -> None:
        self.lots = lots

    async def pending_detail(self, limit: int = 0, statuses: list[str] | None = None) -> AsyncIterator[dict]:
        for lot in self.lots[: limit or None]:
            yield lot


@pytest.fixture
async def storage() -> AsyncIterator[MongoStorage]:
    """``MongoStorage`` площадки ``bep`` во временной коллекции базы ``trading_test``.

    Без Mongo — skip; в CI (``REQUIRE_MONGO=1``) — ошибка, чтобы тесты
    хранилища не выпадали из прогона молча.
    """
    client = AsyncMongoClient(
        os.environ.get("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=2000
    )
    try:
        await client.admin.command("ping")
    except PyMongoError as exc:
        await client.close()
        if os.environ.get("REQUIRE_MONGO"):
            pytest.fail(f"Mongo недоступна: {exc}")
        pytest.skip(f"Mongo недоступна: {exc}")
    s = MongoStorage("bep", client=client, db_name="trading_test", collection=f"test_{uuid4().hex[:8]}")
    await s.__aenter__()
    yield s
    await s.collection.drop()
    await s.close()
    await client.close()
