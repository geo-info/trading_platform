"""Реестр площадок: имя -> класс, один на все движки.

Фреймворк реестра не держит намеренно — это забота приложения. Площадку
регистрирует базовый класс её движка в ``__init_subclass__``: площадка — это
класс, объявивший ``DOMAIN``. Примеси и детальные парсеры (``detail_of``)
домена сами не объявляют и в реестр не попадают.

Реестр заполняется при импорте модулей площадок; импортировать их все разом —
дело ``tp.platforms``.

    from tp.platforms import platforms
    platforms()            # все площадки
    platforms(Kendo)       # площадки одного движка
"""

from __future__ import annotations

from collector import Crawler

_PLATFORMS: dict[str, type[Crawler]] = {}


def register(cls: type[Crawler]) -> None:
    """Добавить площадку. Имя уникально между движками: по нему ключ лота и коллекция."""
    if (other := _PLATFORMS.get(cls.name)) is not None and other is not cls:
        raise ValueError(f"площадка {cls.name!r} уже есть: {other.__module__}.{other.__qualname__}")
    _PLATFORMS[cls.name] = cls


def platforms(engine: type[Crawler] | None = None) -> dict[str, type[Crawler]]:
    """Площадки в порядке объявления: все или только движка ``engine``."""
    return {name: cls for name, cls in _PLATFORMS.items() if engine is None or issubclass(cls, engine)}
