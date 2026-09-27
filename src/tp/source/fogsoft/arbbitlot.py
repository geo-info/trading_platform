"""АРБбитЛот — банкротные торги, движок iTender.

Сертификат площадки просрочен на их стороне, CA-бандл тут не помогает,
поэтому проверка TLS отключена. Это снимает и защиту от подмены трафика —
цена за доступ к сайту, который иначе не открыть вовсе.

uv run python -m run_all arbbitlot
"""

from __future__ import annotations

from tp.common import narrow
from tp.fogsoft import TenderFogsoft


class Arbbitlot(TenderFogsoft):
    name = "arbbitlot"
    DOMAIN = "https://torgi.arbbitlot.ru"
    settings = narrow(skip_tls_verify=True)
