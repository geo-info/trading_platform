"""Площадки на движке Kendo-ETP."""

from __future__ import annotations

from dataclasses import replace

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


class EtpProfit(Kendo):
    """ЭТП Профит. Переехала с btorg на Kendo (2026-09): старый листинг
    ``/etp/trade/list.html`` уводит на главную.

    Сервер не отдаёт промежуточный сертификат «GlobalSign GCC R6 AlphaSSL CA
    2025» — проверка TLS пока выключена. Когда сертификат появится в
    ``core/certs/etp_profit.pem``, заменить на ``extra_ca_cert``, как у meta_invest.
    """

    name = "etp_profit"
    DOMAIN = "https://etp-profit.ru"
    settings = replace(Kendo.settings, skip_tls_verify=True)


class PtpCenter(Kendo):
    """ПТП-Центр. Переехала с btorg на Kendo (2026-09); блок лота — второй
    шаблон (номер в ``span.normal``, цена в ``div.fs24``)."""

    name = "ptp_center"
    DOMAIN = "https://ptp-center.ru"
