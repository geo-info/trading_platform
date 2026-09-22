"""Арбитат — банкротные торги, движок iTender.

uv run python -m tp.platform.arbitat
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Arbitat(TenderFogsoft):
    name = "arbitat"
    DOMAIN = "http://arbitat.ru"


if __name__ == "__main__":
    main(Arbitat)
