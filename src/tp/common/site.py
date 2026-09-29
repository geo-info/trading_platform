"""Площадка вообще: то, что одинаково у всех движков.

Адрес листинга выводится из домена площадки и пути листинга движка, ответ
не-200 — ошибка, а не пустая страница, настройки площадки — настройки
движка плюс её особенность.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any, ClassVar

from collector import Crawler, Response, Settings


def check_status(response: Response) -> None:
    """Не-200 — ошибка запроса, а не пустая страница: иначе площадка с
    переехавшим листингом выглядела бы обходом без лотов."""
    if response.status != 200:
        raise ValueError(f"{response.status} для {response.request.url}")


def narrow(engine: type[Crawler], **overrides: Any) -> Settings:
    """Настройки площадки: настройки движка плюс её особенность (хук, сертификат, TLS).

    Через ``replace``, а не конструктором: площадка со своей причудой не
    теряет общие ``delay`` и ``timeout`` движка, когда те поменяются.
    """
    return replace(engine.settings, **overrides)


class Site(Crawler):
    """Площадка: ``name`` и ``DOMAIN`` задаёт она, ``LISTING_PATH`` — движок.

    Площадка может переопределить и путь листинга (у части rus-on он свой).
    У базы движка домена нет, и адреса листинга тоже.
    """

    DOMAIN: ClassVar[str]
    LISTING_PATH: ClassVar[str] = ""

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        if domain := getattr(cls, "DOMAIN", None):
            cls.start_urls = [f"{domain.rstrip('/')}/{cls.LISTING_PATH}"]
