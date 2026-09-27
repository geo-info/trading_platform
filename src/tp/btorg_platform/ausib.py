"""Аукционы Сибири — банкротные торги, движок btorg (edoc-ETP).

Пускает только с cookie: первый ответ — редирект на тот же адрес, cookie
хранит сессия фреймворка.

uv run python -m run_all ausib
"""

from __future__ import annotations

from tp.btorg import TenderBtorg


class Ausib(TenderBtorg):
    name = "ausib"
    DOMAIN = "https://ausib.ru"
