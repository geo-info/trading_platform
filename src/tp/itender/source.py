"""Площадки движка iTender: имя, домен и особенность, если есть.

Настройки HTTP и параметры прогона — движка (``ITender``); площадка со своей
причудой сужает их через ``narrow``: хук антибота, свой сертификат,
отключённая проверка TLS.
"""

from __future__ import annotations

from core.hooks.inprotect import solve_inprotect
from tp.common.site import narrow
from tp.itender.base import ITender


class Alfalot(ITender):
    """АЛЬФАЛОТ. На входе JS-проверка отпечатка inprotect — её проходит хук."""

    name = 'alfalot'
    DOMAIN = 'https://bankrupt.alfalot.ru'
    settings = narrow(ITender, concurrency = 1, response_hooks = [solve_inprotect])


class Arbbitlot(ITender):
    """АРБбитЛот. Сертификат просрочен на их стороне — проверка TLS отключена."""

    name = 'arbbitlot'
    DOMAIN = 'https://torgi.arbbitlot.ru'
    settings = narrow(ITender, skip_tls_verify = True)


class Arbitat(ITender):
    """Арбитат."""

    name = 'arbitat'
    DOMAIN = 'http://arbitat.ru'


class Bep(ITender):
    """Балтийская электронная площадка."""

    name = 'bep'
    DOMAIN = 'https://bankruptcy.bepspb.ru'


class Centerr(ITender):
    """Центр Реализации."""

    name = 'centerr'
    DOMAIN = 'https://bankrupt.centerr.ru'


class Etb(ITender):
    """ЕЭТП / ets24.ru."""

    name = 'etb'
    DOMAIN = 'http://bankrupt.ets24.ru'


class EtpuBankrupt(ITender):
    """Уральская электронная торговая площадка."""

    name = 'etpu_bankrupt'
    DOMAIN = 'https://bankrupt.etpu.ru'


class Etpugra(ITender):
    """ЭТП Югра."""

    name = 'etpugra'
    DOMAIN = 'https://etpugra.ru'


class GloriaService(ITender):
    """ЭТП Регион (GloriaService)."""

    name = 'gloria_service'
    DOMAIN = 'https://gloriaservice.ru'


class MetaInvest(ITender):
    """МЕТА-ИНВЕСТ. Сервер не досылает промежуточный сертификат — подставляем свой;
    путь к PEM фреймворк разрешает относительно этого файла."""

    name = 'meta_invest'
    DOMAIN = 'https://meta-invest.ru'
    settings = narrow(ITender, extra_ca_cert = '../../core/certs/meta_invest.pem')


class TenderOne(ITender):
    """Tender Technologies."""

    name = 'tender_one'
    DOMAIN = 'https://bankrupt.tender.one'


class Tendergarant(ITender):
    """ТЕНДЕР ГАРАНТ."""

    name = 'tendergarant'
    DOMAIN = 'https://tendergarant.com'


class Utender(ITender):
    """uTender."""

    name = 'utender'
    DOMAIN = 'http://utender.ru'


class UtpLot(ITender):
    """Объединённая торговая площадка."""

    name = 'utp_lot'
    DOMAIN = 'https://bankrupt.utpl.ru'


class YuzhnyyEtp(ITender):
    """ЮЭТП."""

    name = 'yuzhnyy_etp'
    DOMAIN = 'https://torgibankrot.ru'


class Zakazrf(ITender):
    """ЭТП Заказ РФ."""

    name = 'zakazrf'
    DOMAIN = 'http://bankrot.zakazrf.ru'


#: Все площадки движка: имя -> класс.
PLATFORMS: dict[str, type[ITender]] = {
    cls.name: cls for cls in ITender.__subclasses__() if cls.__module__ == __name__
}
