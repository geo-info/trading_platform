"""ЕЭТП / ets24.ru — банкротные торги, движок iTender.

Пейджера на листинге нет — площадка укладывается в одну страницу.
``find_next_target`` вернёт ``None``, и обход честно закончится на первой.

uv run python -m run_all etb
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class Etb(TenderFogsoft):
    name = "etb"
    DOMAIN = "http://bankrupt.ets24.ru"
