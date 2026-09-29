"""Площадки движка Kendo-ETP: имя, домен и особенность, если есть.

Настройки HTTP и параметры прогона — движка (``Kendo``); площадка со своей
причудой сужает их через ``tp.common.site.narrow``.
"""

from __future__ import annotations

from tp.kendo.base import Kendo


class TradeAlliance(Kendo):
    """Альянс Трэйд."""

    name = 'trade_alliance'
    DOMAIN = 'https://trade-alliance.ru'


class Seltim(Kendo):
    """Селтим."""

    name = 'seltim'
    DOMAIN = 'https://bankrupt.seltim.ru'


class ElectroTorgi(Kendo):
    """Электро-Торги."""

    name = 'electro_torgi'
    DOMAIN = 'https://bankrotstvo.electro-torgi.ru'


class Torgi82(Kendo):
    """Торги82. Коды статусов другие, чем у остальных: «Объявлен» — 2;
    статус ищется по названию, так что это ничего не меняет."""

    name = 'torgi82'
    DOMAIN = 'https://lot.torgi82.ru'


class Vetp(Kendo):
    """ВЭТП. Домен кириллический — в punycode его переводит curl; коды статусов как у torgi82."""

    name = 'vetp'
    DOMAIN = 'https://банкрот.вэтп.рф'


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Kendo]] = {
    cls.name: cls for cls in Kendo.__subclasses__() if cls.__module__ == __name__
}
