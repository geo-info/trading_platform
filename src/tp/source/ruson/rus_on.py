"""РОССИЯ ОнЛайн — банкротные торги, движок rus-on.

uv run python -m run_all rus_on
"""

from __future__ import annotations

from tp.ruson import TenderRuson


class RusOn(TenderRuson):
    name = "rus_on"
    DOMAIN = "https://rus-on.ru"
