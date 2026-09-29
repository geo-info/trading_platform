"""Площадки на движке Kendo-ETP."""

from __future__ import annotations

from tp.kendo.base import Kendo


class TradeAlliance(Kendo):
    """Альянс Трэйд."""

    name = "trade_alliance"
    DOMAIN = "https://trade-alliance.ru"


class Seltim(Kendo):
    """Селтим."""

    name = "seltim"
    DOMAIN = "https://bankrupt.seltim.ru"


class ElectroTorgi(Kendo):
    """Электро-Торги."""

    name = "electro_torgi"
    DOMAIN = "https://bankrotstvo.electro-torgi.ru"


class Torgi82(Kendo):
    """Торги82."""

    name = "torgi82"
    DOMAIN = "https://lot.torgi82.ru"


class Vetp(Kendo):
    """ВЭТП. Домен кириллический — в punycode его переводит curl."""

    name = "vetp"
    DOMAIN = "https://банкрот.вэтп.рф"


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Kendo]] = {
    cls.name: cls for cls in Kendo.__subclasses__() if cls.__module__ == __name__
}
