"""ПТП-Центр — банкротные торги, движок btorg (edoc-ETP).

uv run python -m run_all ptp_center
"""

from __future__ import annotations

from tp.btorg import TenderBtorg


class PtpCenter(TenderBtorg):
    name = "ptp_center"
    DOMAIN = "https://ptp-center.ru"
