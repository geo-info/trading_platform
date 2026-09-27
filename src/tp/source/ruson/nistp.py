"""Новые информационные сервисы — банкротные торги, движок rus-on.

uv run python -m run_all nistp
"""

from __future__ import annotations

from tp.ruson import TenderRuson


class Nistp(TenderRuson):
    name = "nistp"
    DOMAIN = "https://nistp.ru"
