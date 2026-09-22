"""ЮЭТП — банкротные торги, движок iTender.

uv run python -m tp.platform.yuzhnyy_etp
"""

from __future__ import annotations

from tp.base import TenderFogsoft, main


class YuzhnyyEtp(TenderFogsoft):
    name = "yuzhnyy_etp"
    DOMAIN = "https://torgibankrot.ru"


if __name__ == "__main__":
    main(YuzhnyyEtp)
