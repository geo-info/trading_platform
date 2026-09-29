from __future__ import annotations

from collector import Settings

from core.conf import conf
from tp.common import SearchParams
from tp.kendo.base import ACTIVE, Kendo


class TradeAlliance(Kendo):
    """Альянс Трэйд."""

    name = 'trade_alliance'
    DOMAIN = 'https://trade-alliance.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Seltim(Kendo):
    """Селтим."""

    name = 'seltim'
    DOMAIN = 'https://bankrupt.seltim.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class ElectroTorgi(Kendo):
    """Электро-Торги."""

    name = 'electro_torgi'
    DOMAIN = 'https://bankrotstvo.electro-torgi.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Torgi82(Kendo):
    """Торги82. Коды статусов другие, чем у остальных: «Объявлен» — 2;
    статус ищется по названию, так что это ничего не меняет."""

    name = 'torgi82'
    DOMAIN = 'https://lot.torgi82.ru'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


class Vetp(Kendo):
    """ВЭТП. Домен кириллический — в punycode его переводит curl; коды статусов как у torgi82."""

    name = 'vetp'
    DOMAIN = 'https://банкрот.вэтп.рф'

    settings = Settings(
        concurrency = 1,
        delay = conf.parsing.delay,
        timeout = conf.parsing.http_timeout,
        max_errors = 50
    )

    params = SearchParams(statuses = ACTIVE, max_pages = conf.parsing.max_pages)


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Kendo]] = {
    cls.name: cls for cls in Kendo.__subclasses__() if cls.__module__ == __name__
}
