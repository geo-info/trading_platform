"""Настройки приложения: одно место, где читается окружение.

Раньше каждый модуль лазил в ``os.getenv`` сам, и узнать, какие вообще есть
ручки, можно было только грепом. Здесь они перечислены, типизированы и имеют
значения по умолчанию, при которых всё работает без единой переменной
окружения — локальная Mongo из ``compose.yaml`` и есть этот случай.

Читается из окружения и из ``.env`` в корне репозитория; переменные окружения
имеют приоритет над файлом, чтобы настройки из CI или docker не перетирались
чьим-то локальным ``.env``.

    from core.settings import settings
    settings.mongo_uri
"""

from __future__ import annotations

from datetime import date
from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

#: src/core/settings.py -> корень репозитория
ROOT_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=ROOT_DIR / ".env",
        env_file_encoding="utf-8",
        # Лишняя переменная в .env — не повод падать: там же лежат ключи
        # для соседних инструментов.
        extra="ignore",
    )

    #: Адрес Mongo. По умолчанию — та, что поднимает compose.yaml.
    mongo_uri: str = "mongodb://localhost:27017"
    mongo_db: str = "trading"
    #: Все площадки пишут в одну коллекцию, различает их поле source.
    mongo_collection: str = "lots"

    #: Предохранитель обхода: сколько страниц листинга брать с площадки.
    #: Без потолка ошибка в пагинации крутится вечно и ничем не выдаёт себя.
    max_pages: int = Field(default=100, ge=1)

    #: Окно обхода по времени: листинг листается, пока на странице есть лот с
    #: приёмом заявок не раньше этой даты. Число страниц даёт у площадок разные
    #: окна (у одной 20 страниц — две недели, у другой — четыре года), дата —
    #: одно для всех. ``None`` — без окна, только ``max_pages``.
    since: date | None = None

    #: Пауза между запросами к одной площадке, секунды. Это потолок частоты
    #: на весь обход площадки, а не пауза «на воркера».
    delay: float = Field(default=0.5, ge=0)

    #: Сколько площадок обходить одновременно. Они на разных серверах и друг
    #: другу не мешают — в отличие от параллелизма внутри одной площадки,
    #: который упирается в её же пропускную способность и ничего не даёт.
    platform_concurrency: int = Field(default=16, ge=1)

    #: Таймаут HTTP-запроса, секунды.
    http_timeout: float = Field(default=60.0, gt=0)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Настройки одним экземпляром на процесс.

    Кэш нужен не ради скорости, а ради единственности: иначе два модуля
    прочитают ``.env`` в разные моменты и разойдутся в значениях.
    """
    return Settings()


settings = get_settings()
