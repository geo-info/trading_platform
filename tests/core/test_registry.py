"""Реестр площадок: регистрирует класс, объявивший DOMAIN; имена уникальны между движками."""

from __future__ import annotations

import pytest

import core.registry as registry
import tp.platforms  # noqa: F401  # заполняет реестр при сборке тестов
from core.registry import platforms, register
from tp.btorg.base import Btorg
from tp.itender.base import ITender
from tp.kendo.base import Kendo
from tp.kendo.detail import detail_of
from tp.ruson.base import Ruson


@pytest.fixture
def isolated(monkeypatch: pytest.MonkeyPatch) -> dict:
    """Пустой реестр на время теста: тестовые классы не попадают в настоящий."""
    fresh: dict = {}
    monkeypatch.setattr(registry, "_PLATFORMS", fresh)
    return fresh


def test_все_площадки_всех_движков() -> None:
    assert len(platforms()) == 32
    assert {engine.__name__: len(platforms(engine)) for engine in (ITender, Kendo, Btorg, Ruson)} == {
        "ITender": 16,
        "Kendo": 5,
        "Btorg": 6,
        "Ruson": 5,
    }


def test_площадка_с_доменом_регистрируется(isolated: dict) -> None:
    class Some(Kendo):
        name = "some"
        DOMAIN = "https://some.ru"

    assert isolated == {"some": Some}
    assert Some.start_urls == ["https://some.ru/lots"]


def test_класс_без_домена_не_площадка(isolated: dict) -> None:
    class Mixin(Kendo):
        name = "mixin"

    assert isolated == {}


def test_detail_of_не_регистрирует(isolated: dict) -> None:
    class Some(Kendo):
        name = "some"
        DOMAIN = "https://some.ru"

    detail_of(Some)
    assert list(isolated) == ["some"]


def test_дубль_имени_ошибка(isolated: dict) -> None:
    class First(Kendo):
        name = "dup"
        DOMAIN = "https://a.ru"

    with pytest.raises(ValueError, match="площадка 'dup' уже есть"):

        class Second(Btorg):
            name = "dup"
            DOMAIN = "https://b.ru"


def test_повторная_регистрация_того_же_класса_безвредна(isolated: dict) -> None:
    class Some(Kendo):
        name = "some"
        DOMAIN = "https://some.ru"

    register(Some)
    assert isolated == {"some": Some}


def test_фильтр_по_движку(isolated: dict) -> None:
    class A(Kendo):
        name = "a"
        DOMAIN = "https://a.ru"

    class B(Btorg):
        name = "b"
        DOMAIN = "https://b.ru"

    assert platforms(Kendo) == {"a": A}
    assert platforms() == {"a": A, "b": B}
