"""ВЭТП — банкротные торги, движок Kendo-ETP.

Домен кириллический: хранится в Unicode, в punycode его переводит curl.

uv run python -m run_all vetp
"""

from __future__ import annotations

from tp.kendo import TenderKendo


class Vetp(TenderKendo):
    name = "vetp"
    DOMAIN = "https://банкрот.вэтп.рф"
