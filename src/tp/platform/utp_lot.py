"""Объединённая торговая площадка — банкротные торги, движок iTender.

uv run python -m tp.platform.utp_lot
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class UtpLot(TenderFogsoft):
    name = "utp_lot"
    DOMAIN = "https://bankrupt.utpl.ru"


if __name__ == "__main__":
    main(UtpLot)
