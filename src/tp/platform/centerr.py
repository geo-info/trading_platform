"""Центр Реализации — банкротные торги, движок iTender.

uv run python -m tp.platform.centerr
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Centerr(TenderFogsoft):
    name = "centerr"
    DOMAIN = "https://bankrupt.centerr.ru"


if __name__ == "__main__":
    main(Centerr)
