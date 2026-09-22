"""Уральская электронная торговая площадка — банкротные торги, движок iTender.

uv run python -m tp.platform.etpu_bankrupt
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class EtpuBankrupt(TenderFogsoft):
    name = "etpu_bankrupt"
    DOMAIN = "https://bankrupt.etpu.ru"


if __name__ == "__main__":
    main(EtpuBankrupt)
