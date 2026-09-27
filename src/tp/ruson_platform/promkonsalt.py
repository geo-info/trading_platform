"""Промконсалт — банкротные торги, движок rus-on.

Листинг лежит в корне сайта, а не в ``bankrot/``.

uv run python -m run_all promkonsalt
"""

from __future__ import annotations

from tp.ruson import TenderRuson


class Promkonsalt(TenderRuson):
    name = "promkonsalt"
    DOMAIN = "https://promkonsalt.ru"
    LISTING_PATH = "tradelist.php"
