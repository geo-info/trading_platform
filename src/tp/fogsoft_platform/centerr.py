"""Центр Реализации — банкротные торги, движок iTender.

uv run python -m run_all centerr
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class Centerr(TenderFogsoft):
    name = "centerr"
    DOMAIN = "https://bankrupt.centerr.ru"
