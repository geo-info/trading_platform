"""ТЕНДЕР ГАРАНТ — банкротные торги, движок iTender.

uv run python -m run_all tendergarant
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class Tendergarant(TenderFogsoft):
    name = "tendergarant"
    DOMAIN = "https://tendergarant.com"
