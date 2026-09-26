"""ЮЭТП — банкротные торги, движок iTender.

uv run python -m tp.platform.run_all yuzhnyy_etp
"""

from __future__ import annotations

from tp.base import TenderFogsoft


class YuzhnyyEtp(TenderFogsoft):
    name = "yuzhnyy_etp"
    DOMAIN = "https://torgibankrot.ru"
