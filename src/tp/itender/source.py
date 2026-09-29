from __future__ import annotations

from collector import Settings

from core.conf import conf
from core.hooks.inprotect import solve_inprotect
from tp.itender.base import ITender, ITenderParams


class Alfalot(ITender):
    name = "alfalot"
    DOMAIN = "https://bankrupt.alfalot.ru"

    settings = Settings(
        concurrency=1, delay=0.5, timeout=60.0, max_errors=50, response_hooks=[solve_inprotect]
    )

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Arbbitlot(ITender):
    name = "arbbitlot"
    DOMAIN = "https://torgi.arbbitlot.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50, skip_tls_verify=True)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Arbitat(ITender):
    name = "arbitat"
    DOMAIN = "http://arbitat.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Bep(ITender):
    name = "bep"
    DOMAIN = "https://bankruptcy.bepspb.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Centerr(ITender):
    name = "centerr"
    DOMAIN = "https://bankrupt.centerr.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Etb(ITender):
    name = "etb"
    DOMAIN = "http://bankrupt.ets24.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class EtpuBankrupt(ITender):
    name = "etpu_bankrupt"
    DOMAIN = "https://bankrupt.etpu.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Etpugra(ITender):
    name = "etpugra"
    DOMAIN = "https://etpugra.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class GloriaService(ITender):
    name = "gloria_service"
    DOMAIN = "https://gloriaservice.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class MetaInvest(ITender):
    name = "meta_invest"
    DOMAIN = "https://meta-invest.ru"

    settings = Settings(
        concurrency=5,
        delay=0.5,
        timeout=60.0,
        max_errors=50,
        # Сервер не досылает промежуточный сертификат; путь — от этого файла.
        extra_ca_cert="../../core/certs/meta_invest.pem",
    )

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class TenderOne(ITender):
    name = "tender_one"
    DOMAIN = "https://bankrupt.tender.one"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Tendergarant(ITender):
    name = "tendergarant"
    DOMAIN = "https://tendergarant.com"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Utender(ITender):
    name = "utender"
    DOMAIN = "http://utender.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class UtpLot(ITender):
    name = "utp_lot"
    DOMAIN = "https://bankrupt.utpl.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class YuzhnyyEtp(ITender):
    name = "yuzhnyy_etp"
    DOMAIN = "https://torgibankrot.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)


class Zakazrf(ITender):
    name = "zakazrf"
    DOMAIN = "http://bankrot.zakazrf.ru"

    settings = Settings(concurrency=5, delay=0.5, timeout=60.0, max_errors=50)

    params = ITenderParams(max_pages=conf.parsing.max_pages)
