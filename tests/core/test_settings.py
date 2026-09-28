"""Настройки: группы, имена переменных окружения и умолчания.

``_env_file=None`` — не читать локальный ``.env``: тесты не должны зависеть от
того, что лежит на машине разработчика.
"""

from __future__ import annotations

from datetime import date

import pytest

from core.conf import MongoSettings, ParsingSettings, Settings, get_settings


@pytest.fixture(autouse=True)
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Переменные настроек из окружения машины в тест не протекают."""
    for name in (
        "MONGO_URI",
        "MONGO_DB",
        "MONGO_COLLECTION",
        "MAX_PAGES",
        "SINCE",
        "DELAY",
        "PLATFORM_CONCURRENCY",
        "HTTP_TIMEOUT",
    ):
        monkeypatch.delenv(name, raising=False)


def test_умолчания_работают_без_окружения() -> None:
    mongo = MongoSettings(_env_file=None)
    parsing = ParsingSettings(_env_file=None)
    assert (mongo.uri, mongo.db, mongo.collection) == ("mongodb://localhost:27017", "trading", "lots")
    assert (parsing.max_pages, parsing.since, parsing.delay) == (100, None, 0.5)
    assert (parsing.platform_concurrency, parsing.http_timeout) == (16, 60.0)


def test_имена_переменных_прежние(monkeypatch: pytest.MonkeyPatch) -> None:
    """MONGO_URI, MAX_PAGES и т. д. — как в README: .env и CI не надо трогать."""
    monkeypatch.setenv("MONGO_URI", "mongodb://db:27017")
    monkeypatch.setenv("MONGO_DB", "trading_check")
    monkeypatch.setenv("MONGO_COLLECTION", "lots_v2")
    monkeypatch.setenv("MAX_PAGES", "30")
    monkeypatch.setenv("SINCE", "2026-06-01")
    monkeypatch.setenv("DELAY", "1.5")
    mongo = MongoSettings(_env_file=None)
    parsing = ParsingSettings(_env_file=None)
    assert (mongo.uri, mongo.db, mongo.collection) == ("mongodb://db:27017", "trading_check", "lots_v2")
    assert (parsing.max_pages, parsing.since, parsing.delay) == (30, date(2026, 6, 1), 1.5)


def test_группы_не_видят_переменных_друг_друга(monkeypatch: pytest.MonkeyPatch) -> None:
    """Переменная другой группы — лишняя, а не ошибка: обе читают один .env."""
    monkeypatch.setenv("MONGO_URI", "mongodb://db:27017")
    monkeypatch.setenv("MAX_PAGES", "30")
    assert "max_pages" not in MongoSettings(_env_file=None).model_dump()
    assert "uri" not in ParsingSettings(_env_file=None).model_dump()


def test_неверное_значение_отказывает(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_PAGES", "0")
    with pytest.raises(ValueError, match="max_pages"):
        ParsingSettings(_env_file=None)


def test_все_настройки_по_группам() -> None:
    settings = get_settings()
    assert isinstance(settings, Settings)
    assert isinstance(settings.mongo, MongoSettings)
    assert isinstance(settings.parsing, ParsingSettings)
    assert get_settings() is settings  # один экземпляр на процесс
