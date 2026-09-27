"""Региональная торговая площадка — банкротные торги, движок btorg (edoc-ETP).

uv run python -m run_all regtorg
"""

from __future__ import annotations

from tp.btorg import TenderBtorg


class Regtorg(TenderBtorg):
    name = "regtorg"
    DOMAIN = "https://regtorg.com"
