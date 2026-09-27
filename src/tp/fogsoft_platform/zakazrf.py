"""ЭТП Заказ РФ — банкротные торги, движок iTender.

uv run python -m run_all zakazrf
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class Zakazrf(TenderFogsoft):
    name = "zakazrf"
    DOMAIN = "http://bankrot.zakazrf.ru"
