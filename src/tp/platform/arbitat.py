"""Арбитат — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all arbitat
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class Arbitat(TenderFogsoft):
    name = "arbitat"
    DOMAIN = "http://arbitat.ru"
