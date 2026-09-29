"""Все площадки всех движков: импорт модулей площадок заполняет ``core.registry``.

    from tp.platforms import platforms
    platforms()["centerr"]
"""

from __future__ import annotations

import tp.btorg.source
import tp.itender.source
import tp.kendo.source
import tp.ruson.source  # noqa: F401 — импорт ради регистрации площадок
from core.registry import platforms

__all__ = ["platforms"]
