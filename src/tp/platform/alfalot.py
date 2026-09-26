"""АЛЬФАЛОТ — банкротные торги, движок iTender.

На входе стоит JS-проверка отпечатка inprotect, и без неё листинг
не приходит вообще. Она целиком живёт в хуке ``tp.hooks.inprotect``.

uv run python -m tp.platform.run_all alfalot
"""

from __future__ import annotations

from tp.base import TenderFogsoft, narrow
from tp.hooks.inprotect import solve_inprotect


class Alfalot(TenderFogsoft):
    name = "alfalot"
    DOMAIN = "https://bankrupt.alfalot.ru"
    settings = narrow(response_hooks=(solve_inprotect,))
