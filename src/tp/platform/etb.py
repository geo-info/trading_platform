"""ЕЭТП / ets24.ru — банкротные торги, движок iTender.

Пейджера на листинге нет — площадка укладывается в одну страницу.
``find_next_target`` вернёт ``None``, и обход честно закончится на первой.

uv run python -m tp.platform.etb
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Etb(TenderFogsoft):
    name = "etb"
    DOMAIN = "http://bankrupt.ets24.ru"


if __name__ == "__main__":
    main(Etb)
