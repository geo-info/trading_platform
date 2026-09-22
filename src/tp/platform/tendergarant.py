"""ТЕНДЕР ГАРАНТ — банкротные торги, движок iTender.

uv run python -m tp.platform.tendergarant
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Tendergarant(TenderFogsoft):
    name = "tendergarant"
    DOMAIN = "https://tendergarant.com"


if __name__ == "__main__":
    main(Tendergarant)
