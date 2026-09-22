"""ЭТП Заказ РФ — банкротные торги, движок iTender.

uv run python -m tp.platform.zakazrf
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Zakazrf(TenderFogsoft):
    name = "zakazrf"
    DOMAIN = "http://bankrot.zakazrf.ru"


if __name__ == "__main__":
    main(Zakazrf)
