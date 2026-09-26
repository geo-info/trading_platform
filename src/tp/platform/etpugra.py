"""ЭТП Югра — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all etpugra
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class Etpugra(TenderFogsoft):
    name = "etpugra"
    DOMAIN = "https://etpugra.ru"
