"""Площадки на движке iTender (Fogsoft) — наследники ``TenderFogsoft``.

Площадке достаточно имени и домена; особенность, если есть, — через
``narrow``: хук антибота, свой сертификат, отключённая проверка TLS.
"""

from __future__ import annotations

from core.hooks.inprotect import solve_inprotect
from tp.delete.fogsoft import TenderFogsoft, narrow


class Alfalot(TenderFogsoft):
    """АЛЬФАЛОТ. На входе JS-проверка отпечатка inprotect — её проходит хук."""

    name = "alfalot"
    DOMAIN = "https://bankrupt.alfalot.ru"
    settings = narrow(response_hooks=(solve_inprotect,))


class Arbbitlot(TenderFogsoft):
    """АРБбитЛот. Сертификат просрочен на их стороне — проверка TLS отключена."""

    name = "arbbitlot"
    DOMAIN = "https://torgi.arbbitlot.ru"
    settings = narrow(skip_tls_verify=True)


class Arbitat(TenderFogsoft):
    """Арбитат."""

    name = "arbitat"
    DOMAIN = "http://arbitat.ru"


class Bep(TenderFogsoft):
    """Балтийская электронная площадка."""

    name = "bep"
    DOMAIN = "https://bankruptcy.bepspb.ru"


class Centerr(TenderFogsoft):
    """Центр Реализации."""

    name = "centerr"
    DOMAIN = "https://bankrupt.centerr.ru"


class Etb(TenderFogsoft):
    """ЕЭТП / ets24.ru."""

    name = "etb"
    DOMAIN = "http://bankrupt.ets24.ru"


class EtpuBankrupt(TenderFogsoft):
    """Уральская электронная торговая площадка."""

    name = "etpu_bankrupt"
    DOMAIN = "https://bankrupt.etpu.ru"


class Etpugra(TenderFogsoft):
    """ЭТП Югра."""

    name = "etpugra"
    DOMAIN = "https://etpugra.ru"


class GloriaService(TenderFogsoft):
    """ЭТП Регион (GloriaService)."""

    name = "gloria_service"
    DOMAIN = "https://gloriaservice.ru"


class MetaInvest(TenderFogsoft):
    """МЕТА-ИНВЕСТ. Сервер не досылает промежуточный сертификат — подставляем свой.

    Путь к PEM фреймворк разрешает относительно файла площадки.
    """

    name = "meta_invest"
    DOMAIN = "https://meta-invest.ru"
    settings = narrow(extra_ca_cert="../core/certs/meta_invest.pem")


class TenderOne(TenderFogsoft):
    """Tender Technologies."""

    name = "tender_one"
    DOMAIN = "https://bankrupt.tender.one"


class Tendergarant(TenderFogsoft):
    """ТЕНДЕР ГАРАНТ."""

    name = "tendergarant"
    DOMAIN = "https://tendergarant.com"


class Utender(TenderFogsoft):
    """uTender."""

    name = "utender"
    DOMAIN = "http://utender.ru"


class UtpLot(TenderFogsoft):
    """Объединённая торговая площадка."""

    name = "utp_lot"
    DOMAIN = "https://bankrupt.utpl.ru"


class YuzhnyyEtp(TenderFogsoft):
    """ЮЭТП."""

    name = "yuzhnyy_etp"
    DOMAIN = "https://torgibankrot.ru"


class Zakazrf(TenderFogsoft):
    """ЭТП Заказ РФ."""

    name = "zakazrf"
    DOMAIN = "http://bankrot.zakazrf.ru"


#: Все площадки движка — имя -> класс; по нему работает ``tp.run_fogsoft``.
PLATFORMS: dict[str, type[TenderFogsoft]] = {
    cls.name: cls for cls in TenderFogsoft.__subclasses__() if cls.__module__ == __name__
}
