"""Площадки на движке btorg (edoc-ETP)."""

from __future__ import annotations

from tp.btorg.base import Btorg


class Atctrade(Btorg):
    """Аукционный тендерный центр."""

    name = "atctrade"
    DOMAIN = "https://atctrade.ru"


class Ausib(Btorg):
    """Аукционы Сибири. Пускает только с cookie: первый ответ — редирект на тот же
    адрес, cookie хранит сессия фреймворка."""

    name = "ausib"
    DOMAIN = "https://ausib.ru"


class EtpProfit(Btorg):
    """ЭТП Профит. Соединения принимает через раз."""

    name = "etp_profit"
    DOMAIN = "https://etp-profit.ru"


class Aukcioncenter(Btorg):
    """Аукционный центр."""

    name = "aukcioncenter"
    DOMAIN = "https://aukcioncenter.ru"


class Regtorg(Btorg):
    """Региональная торговая площадка."""

    name = "regtorg"
    DOMAIN = "https://regtorg.com"


class PtpCenter(Btorg):
    """ПТП-Центр. Соединения принимает через раз."""

    name = "ptp_center"
    DOMAIN = "https://ptp-center.ru"


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[Btorg]] = {
    cls.name: cls for cls in Btorg.__subclasses__() if cls.__module__ == __name__
}
