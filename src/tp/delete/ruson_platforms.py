"""Площадки на движке rus-on — наследники ``TenderRuson``."""

from __future__ import annotations

from tp.delete.ruson import TenderRuson


class Nistp(TenderRuson):
    """Новые информационные сервисы. Статус — чекбоксы ``trade_state[]``."""

    name = "nistp"
    DOMAIN = "https://nistp.ru"


class ElTorg(TenderRuson):
    """Электронные торги."""

    name = "el_torg"
    DOMAIN = "https://el-torg.com"


class RusOn(TenderRuson):
    """РОССИЯ ОнЛайн."""

    name = "rus_on"
    DOMAIN = "https://rus-on.ru"


class Sistematorg(TenderRuson):
    """Объединённые системы торгов. Листинг в корне сайта, а не в ``bankrot/``."""

    name = "sistematorg"
    DOMAIN = "https://sistematorg.com"
    LISTING_PATH = "tradelist.php"


class Promkonsalt(TenderRuson):
    """Промконсалт. Листинг в корне сайта, а не в ``bankrot/``."""

    name = "promkonsalt"
    DOMAIN = "https://promkonsalt.ru"
    LISTING_PATH = "tradelist.php"


#: Все площадки движка — имя -> класс; по нему работает ``tp.run_ruson``.
PLATFORMS: dict[str, type[TenderRuson]] = {
    cls.name: cls for cls in TenderRuson.__subclasses__() if cls.__module__ == __name__
}
