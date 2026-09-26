"""ЭТП Регион (GloriaService) — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all gloria_service
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class GloriaService(TenderFogsoft):
    name = "gloria_service"
    DOMAIN = "https://gloriaservice.ru"
