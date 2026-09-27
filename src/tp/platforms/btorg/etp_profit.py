"""ЭТП Профит — банкротные торги, движок btorg (edoc-ETP).

uv run python -m run_all etp_profit
"""

from __future__ import annotations

from tp.btorg import TenderBtorg


class EtpProfit(TenderBtorg):
    name = "etp_profit"
    DOMAIN = "https://etp-profit.ru"
