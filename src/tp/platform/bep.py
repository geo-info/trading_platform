"""Балтийская электронная площадка — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all bep
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class Bep(TenderFogsoft):
    name = "bep"
    DOMAIN = "https://bankruptcy.bepspb.ru"
