"""ЭТП Регион (GloriaService) — банкротные торги, движок iTender.

uv run python -m tp.platform.gloria_service
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class GloriaService(TenderFogsoft):
    name = "gloria_service"
    DOMAIN = "https://gloriaservice.ru"


if __name__ == "__main__":
    main(GloriaService)
