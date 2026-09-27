"""Объединённые системы торгов — банкротные торги, движок rus-on.

Листинг лежит в корне сайта, а не в ``bankrot/``.

uv run python -m run_all sistematorg
"""

from __future__ import annotations

from tp.ruson import TenderRuson


class Sistematorg(TenderRuson):
    name = "sistematorg"
    DOMAIN = "https://sistematorg.com"
    LISTING_PATH = "tradelist.php"
