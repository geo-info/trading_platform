"""Электро-Торги — банкротные торги, движок Kendo-ETP.

uv run python -m run_all electro_torgi
"""

from __future__ import annotations

from tp.kendo import TenderKendo


class ElectroTorgi(TenderKendo):
    name = "electro_torgi"
    DOMAIN = "https://bankrotstvo.electro-torgi.ru"
