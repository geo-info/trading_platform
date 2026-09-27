"""ЭТП Регион (GloriaService) — банкротные торги, движок iTender.

uv run python -m run_all gloria_service
"""

from __future__ import annotations

from tp.fogsoft import TenderFogsoft


class GloriaService(TenderFogsoft):
    name = "gloria_service"
    DOMAIN = "https://gloriaservice.ru"
