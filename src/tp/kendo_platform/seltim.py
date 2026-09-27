"""Селтим — банкротные торги, движок Kendo-ETP.

uv run python -m run_all seltim
"""

from __future__ import annotations

from tp.kendo import TenderKendo


class Seltim(TenderKendo):
    name = "seltim"
    DOMAIN = "https://bankrupt.seltim.ru"
