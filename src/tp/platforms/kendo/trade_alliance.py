"""Альянс Трэйд — банкротные торги, движок Kendo-ETP.

uv run python -m run_all trade_alliance
"""

from __future__ import annotations

from tp.kendo import TenderKendo


class TradeAlliance(TenderKendo):
    name = "trade_alliance"
    DOMAIN = "https://trade-alliance.ru"
