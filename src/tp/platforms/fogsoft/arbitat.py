"""Арбитат — банкротные торги, движок iTender.

uv run python -m run_all arbitat
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class Arbitat(TenderFogsoft):
    name = "arbitat"
    DOMAIN = "http://arbitat.ru"
