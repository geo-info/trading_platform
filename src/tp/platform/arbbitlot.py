"""АРБбитЛот — банкротные торги, движок iTender.

Сертификат площадки просрочен на их стороне, CA-бандл тут не помогает,
поэтому проверка TLS отключена. Это снимает и защиту от подмены трафика —
цена за доступ к сайту, который иначе не открыть вовсе.

uv run python -m tp.platform.arbbitlot
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main, narrow


class Arbbitlot(TenderFogsoft):
    name = "arbbitlot"
    DOMAIN = "https://torgi.arbbitlot.ru"
    settings = narrow(skip_tls_verify=True)


if __name__ == "__main__":
    main(Arbbitlot)
