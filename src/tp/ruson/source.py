from __future__ import annotations

from collector import Settings

from core.conf import conf
from tp.common import SearchParams
from tp.ruson.base import ACTIVE, Ruson


class Nistp(Ruson):
    """Новые информационные сервисы. Статус — чекбоксы ``trade_state[]``."""

    name = 'nistp'
    DOMAIN = 'https://nistp.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class ElTorg(Ruson):
    """Электронные торги."""

    name = 'el_torg'
    DOMAIN = 'https://el-torg.com'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class RusOn(Ruson):
    """РОССИЯ ОнЛайн."""

    name = 'rus_on'
    DOMAIN = 'https://rus-on.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Sistematorg(Ruson):
    """Объединённые системы торгов. Листинг в корне сайта, а не в ``bankrot/``."""

    name = 'sistematorg'
    DOMAIN = 'https://sistematorg.com'
    LISTING_PATH = 'tradelist.php'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Promkonsalt(Ruson):
    """Промконсалт. Листинг в корне сайта, а не в ``bankrot/``."""

    name = 'promkonsalt'
    DOMAIN = 'https://promkonsalt.ru'
    LISTING_PATH = 'tradelist.php'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Ruson]] = {
    cls.name: cls for cls in Ruson.__subclasses__() if cls.__module__ == __name__
}
