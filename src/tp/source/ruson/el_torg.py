"""Электронные торги — банкротные торги, движок rus-on.

uv run python -m run_all el_torg
"""

from __future__ import annotations

from tp.ruson import TenderRuson


class ElTorg(TenderRuson):
    name = "el_torg"
    DOMAIN = "https://el-torg.com"
