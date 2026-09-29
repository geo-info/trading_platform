"""Настройки приложения: одно место, где читается окружение.

Раньше каждый модуль лазил в ``os.getenv`` сам, и узнать, какие вообще есть
ручки, можно было только грепом. Здесь они перечислены, типизированы и имеют
значения по умолчанию, при которых всё работает без единой переменной
окружения — локальная Mongo из ``compose.yaml`` и есть этот случай.

Настройки разложены по тому, кого они касаются: ``MongoSettings`` — куда
писать, ``ParsingSettings`` — как обходить площадки. Модулю хранилища незачем
видеть паузу между запросами, а парсеру — адрес базы.

Читается из окружения и из ``.env`` в корне репозитория; переменные окружения
имеют приоритет над файлом, чтобы настройки из CI или docker не перетирались
чьим-то локальным ``.env``. Имена переменных — ``MONGO_URI``, ``MAX_PAGES`` и
т. д., см. README.

    from core.conf import conf
    conf.mongo.uri
    conf.parsing.max_pages
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT_DIR = Path(__file__).resolve().parents[2]

ENV = SettingsConfigDict(env_file=ROOT_DIR / ".env", env_file_encoding="utf-8", extra="ignore")


class MongoSettings(BaseSettings):
    """Куда писать лоты. Переменные — ``MONGO_URI``, ``MONGO_DB``.

    Коллекция своя у каждой площадки и называется её именем, поэтому
    настройки для неё нет.
    """

    model_config = SettingsConfigDict(**ENV, env_prefix="MONGO_")

    #: Адрес Mongo. По умолчанию — та, что поднимает compose.yaml.
    uri: str = "mongodb://localhost:27017"
    db: str = "trading"


class ParsingSettings(BaseSettings):
    model_config = ENV

    since: date | None = None
    delay: float = Field(default=0.5, ge=0)
    max_pages: int = Field(default=100, ge=1)
    platform_concurrency: int = Field(default=16, ge=1)
    http_timeout: float = Field(default=60.0, gt=0)


class Settings(BaseModel):
    """Все настройки приложения, по группам."""

    mongo: MongoSettings = Field(default_factory=MongoSettings)
    parsing: ParsingSettings = Field(default_factory=ParsingSettings)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки одним экземпляром на процесс.

    Кэш нужен не ради скорости, а ради единственности: иначе два модуля
    прочитают ``.env`` в разные моменты и разойдутся в значениях.
    """
    return Settings()


conf = get_settings()
