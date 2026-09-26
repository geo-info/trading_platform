"""МЕТА-ИНВЕСТ — банкротные торги, движок iTender.

Сервер не досылает промежуточный сертификат своей цепочки, и curl, в отличие
от браузера, сам его не подтянет — подставляем свой поверх бандла certifi.
Путь к PEM фреймворк разрешает относительно файла парсера — отсюда ``..``:
сам сертификат лежит на уровень выше, в tp/certs/.

uv run python -m tp.platform.run_all meta_invest
"""

from __future__ import annotations

from tp.base import TenderFogsoft, narrow


class MetaInvest(TenderFogsoft):
    name = "meta_invest"
    DOMAIN = "https://meta-invest.ru"
    settings = narrow(extra_ca_cert="../certs/meta_invest.pem")
