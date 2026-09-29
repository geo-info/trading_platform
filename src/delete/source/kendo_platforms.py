"""Площадки на движке Kendo-ETP — наследники ``TenderKendo``."""

from __future__ import annotations

from tp.delete.kendo import TenderKendo


class TradeAlliance(TenderKendo):
    """Альянс Трэйд."""

    name = "trade_alliance"
    DOMAIN = "https://trade-alliance.ru"


class Seltim(TenderKendo):
    """Селтим."""

    name = "seltim"
    DOMAIN = "https://bankrupt.seltim.ru"


class ElectroTorgi(TenderKendo):
    """Электро-Торги."""

    name = "electro_torgi"
    DOMAIN = "https://bankrotstvo.electro-torgi.ru"


class Torgi82(TenderKendo):
    """Торги82. Коды статусов другие, чем у остальных: «Объявлен» — 2."""

    name = "torgi82"
    DOMAIN = "https://lot.torgi82.ru"


class Vetp(TenderKendo):
    """ВЭТП. Домен кириллический — в punycode его переводит curl; коды статусов как у torgi82."""

    name = "vetp"
    DOMAIN = "https://банкрот.вэтп.рф"


#: Все площадки движка — имя -> класс; по нему работает ``tp.run_kendo``.
PLATFORMS: dict[str, type[TenderKendo]] = {
    cls.name: cls for cls in TenderKendo.__subclasses__() if cls.__module__ == __name__
}
