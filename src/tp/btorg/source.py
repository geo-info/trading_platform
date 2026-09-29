from __future__ import annotations

from collector import Settings

from core.conf import conf
from tp.btorg.base import ACTIVE, Btorg
from tp.common import SearchParams


class Atctrade(Btorg):
    """Аукционный тендерный центр."""

    name = 'atctrade'
    DOMAIN = 'https://atctrade.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Ausib(Btorg):
    """Аукционы Сибири. Пускает только с cookie: первый ответ — редирект на тот же
    адрес, cookie хранит сессия фреймворка."""

    name = 'ausib'
    DOMAIN = 'https://ausib.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class EtpProfit(Btorg):
    """ЭТП Профит. Соединения принимает через раз."""

    name = 'etp_profit'
    DOMAIN = 'https://etp-profit.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Aukcioncenter(Btorg):
    """Аукционный центр."""

    name = 'aukcioncenter'
    DOMAIN = 'https://aukcioncenter.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Regtorg(Btorg):
    """Региональная торговая площадка."""

    name = 'regtorg'
    DOMAIN = 'https://regtorg.com'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class PtpCenter(Btorg):
    """ПТП-Центр. Соединения принимает через раз."""

    name = 'ptp_center'
    DOMAIN = 'https://ptp-center.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Btorg]] = {
    cls.name: cls for cls in Btorg.__subclasses__() if cls.__module__ == __name__
}
