"""ЭТП Югра — банкротные торги, движок iTender.

uv run python -m tp.platform.etpugra
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class Etpugra(TenderFogsoft):
    name = "etpugra"
    DOMAIN = "https://etpugra.ru"


if __name__ == "__main__":
    main(Etpugra)
