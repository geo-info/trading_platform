"""Уральская электронная торговая площадка — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all etpu_bankrupt
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class EtpuBankrupt(TenderFogsoft):
    name = "etpu_bankrupt"
    DOMAIN = "https://bankrupt.etpu.ru"
