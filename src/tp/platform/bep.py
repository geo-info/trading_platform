"""Балтийская электронная площадка — банкротные торги, движок iTender.

uv run python -m tp.platform.bep
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Bep(TenderFogsoft):
    name = "bep"
    DOMAIN = "https://bankruptcy.bepspb.ru"


if __name__ == "__main__":
    main(Bep)
