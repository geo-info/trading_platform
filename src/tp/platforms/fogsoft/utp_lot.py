"""Объединённая торговая площадка — банкротные торги, движок iTender.

uv run python -m run_all utp_lot
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class UtpLot(TenderFogsoft):
    name = "utp_lot"
    DOMAIN = "https://bankrupt.utpl.ru"
