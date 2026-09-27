"""Балтийская электронная площадка — банкротные торги, движок iTender.

uv run python -m run_all bep
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class Bep(TenderFogsoft):
    name = "bep"
    DOMAIN = "https://bankruptcy.bepspb.ru"
