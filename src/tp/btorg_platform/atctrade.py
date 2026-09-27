"""Аукционный тендерный центр — банкротные торги, движок btorg (edoc-ETP).

uv run python -m run_all atctrade
"""

from __future__ import annotations

from tp.btorg import TenderBtorg


class Atctrade(TenderBtorg):
    name = "atctrade"
    DOMAIN = "https://atctrade.ru"
