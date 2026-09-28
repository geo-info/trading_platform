"""Площадки на движке btorg (edoc-ETP) — наследники ``TenderBtorg``."""

from __future__ import annotations

from tp.delete.btorg import TenderBtorg


class Atctrade(TenderBtorg):
    """Аукционный тендерный центр."""

    name = "atctrade"
    DOMAIN = "https://atctrade.ru"


class Ausib(TenderBtorg):
    """Аукционы Сибири. Пускает только с cookie: первый ответ — редирект на тот же
    адрес, cookie хранит сессия фреймворка."""

    name = "ausib"
    DOMAIN = "https://ausib.ru"


class EtpProfit(TenderBtorg):
    """ЭТП Профит. Соединения принимает через раз."""

    name = "etp_profit"
    DOMAIN = "https://etp-profit.ru"


class Aukcioncenter(TenderBtorg):
    """Аукционный центр."""

    name = "aukcioncenter"
    DOMAIN = "https://aukcioncenter.ru"


class Regtorg(TenderBtorg):
    """Региональная торговая площадка."""

    name = "regtorg"
    DOMAIN = "https://regtorg.com"


class PtpCenter(TenderBtorg):
    """ПТП-Центр. Соединения принимает через раз."""

    name = "ptp_center"
    DOMAIN = "https://ptp-center.ru"


#: Все площадки движка — имя -> класс; по нему работает ``tp.run_btorg``.
PLATFORMS: dict[str, type[TenderBtorg]] = {
    cls.name: cls for cls in TenderBtorg.__subclasses__() if cls.__module__ == __name__
}
