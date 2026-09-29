"""Общее для тестов: фикстуры-страницы, офлайн-ответы краулеру, хранилище на Mongo.

Краулер в тестах не ходит в сеть: колбэки (``parse``, ``parse_trade``,
``start_requests``) вызываются напрямую, а ответом служит HTML-фикстура,
завёрнутая в ``Response`` фреймворка. Так проверяется и разбор, и то, какие
запросы краулер отдаёт дальше.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import AsyncIterable, AsyncIterator
from datetime import UTC, datetime, timedelta, tzinfo
from pathlib import Path
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
from collector import Crawler, CrawlerContext, Request, Response
from parsel import Selector
from pymongo import AsyncMongoClient
from pymongo.errors import PyMongoError

import core.db.mongo.storage as storage_module
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


class Clock:
    """Детерминированные часы: каждый вызов ``now()`` на 10 мс позже предыдущего.

    Mongo хранит время с точностью до миллисекунды; две записи подряд на быстрой
    машине попадают в одну и ту же миллисекунду, и сравнения «позже/раньше» мигают.
    """

    STEP = timedelta(milliseconds=10)

    def __init__(self) -> None:
        self._last = datetime.now(UTC)

    def now(self) -> datetime:
        self._last += self.STEP
        return self._last


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    """Часы для хранилища и тестов: ``datetime.now`` в ``core.db.mongo.storage`` идёт через них."""
    c = Clock()

    class FakeDatetime(datetime):
        @classmethod
        def now(cls, tz: tzinfo | None = None) -> datetime:
            return c.now()

    monkeypatch.setattr(storage_module, "datetime", FakeDatetime)
    return c


_MONGO_ERROR: str | None = None  # причина недоступности Mongo: пинг ждём только один раз за сессию


def _mongo_required() -> bool:
    return os.environ.get("REQUIRE_MONGO", "").strip().lower() in {"1", "true", "yes"}


def _unavailable(reason: str) -> None:
    if _mongo_required():
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
async def storage(clock: Clock) -> AsyncIterator[MongoStorage]:
    """``MongoStorage`` площадки ``bep`` во временной коллекции базы ``trading_test``.

    Время записей задают ``clock``-часы. Без Mongo — skip; в CI
    (``REQUIRE_MONGO=1``) — ошибка, чтобы тесты хранилища не выпадали из прогона молча.
    """
    global _MONGO_ERROR
    if _MONGO_ERROR is not None:
        _unavailable(_MONGO_ERROR)
    client = AsyncMongoClient(
        os.environ.get("MONGO_URI", "mongodb://localhost:27017"), serverSelectionTimeoutMS=2000
    )
    try:
        try:
            await client.admin.command("ping")
        except PyMongoError as exc:
            _MONGO_ERROR = f"Mongo недоступна: {exc}"
            _unavailable(_MONGO_ERROR)
        s = MongoStorage("bep", client=client, db_name="trading_test", collection=f"test_{uuid4().hex[:8]}")
        await s.__aenter__()
        try:
            yield s
        finally:
            with contextlib.suppress(PyMongoError):
                await s.collection.drop()
            await s.close()
    finally:
        await client.close()
