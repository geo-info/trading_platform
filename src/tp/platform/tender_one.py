"""Tender Technologies — банкротные торги, движок iTender.

uv run python -m tp.platform.tender_one
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class TenderOne(TenderFogsoft):
    name = "tender_one"
    DOMAIN = "https://bankrupt.tender.one"


if __name__ == "__main__":
    main(TenderOne)
