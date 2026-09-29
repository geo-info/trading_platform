"""Площадки на движке rus-on."""

from __future__ import annotations

from tp.ruson.base import Ruson


class Nistp(Ruson):
    """Новые информационные сервисы."""

    name = "nistp"
    DOMAIN = "https://nistp.ru"


class ElTorg(Ruson):
    """Электронные торги."""

    name = "el_torg"
    DOMAIN = "https://el-torg.com"


class RusOn(Ruson):
    """РОССИЯ ОнЛайн."""

    name = "rus_on"
    DOMAIN = "https://rus-on.ru"


class Sistematorg(Ruson):
    """Объединённые системы торгов. Листинг в корне сайта, а не в ``bankrot/``."""

    name = "sistematorg"
    DOMAIN = "https://sistematorg.com"
    LISTING_PATH = "tradelist.php"


class Promkonsalt(Ruson):
    """Промконсалт. Листинг в корне сайта, а не в ``bankrot/``."""

    name = "promkonsalt"
    DOMAIN = "https://promkonsalt.ru"
    LISTING_PATH = "tradelist.php"
