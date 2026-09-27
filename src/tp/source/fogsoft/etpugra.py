"""ЭТП Югра — банкротные торги, движок iTender.

uv run python -m run_all etpugra
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class Etpugra(TenderFogsoft):
    name = "etpugra"
    DOMAIN = "https://etpugra.ru"
