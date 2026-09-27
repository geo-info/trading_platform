"""Аукционный центр — банкротные торги, движок btorg (edoc-ETP).

uv run python -m run_all aukcioncenter
"""

from __future__ import annotations

from tp.btorg import TenderBtorg


class Aukcioncenter(TenderBtorg):
    name = "aukcioncenter"
    DOMAIN = "https://aukcioncenter.ru"
