"""Tender Technologies — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all tender_one
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class TenderOne(TenderFogsoft):
    name = "tender_one"
    DOMAIN = "https://bankrupt.tender.one"
