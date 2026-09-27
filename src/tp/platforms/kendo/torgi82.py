"""Торги82 — банкротные торги, движок Kendo-ETP.

uv run python -m run_all torgi82
"""

from __future__ import annotations

from tp.kendo import TenderKendo


class Torgi82(TenderKendo):
    name = "torgi82"
    DOMAIN = "https://lot.torgi82.ru"
