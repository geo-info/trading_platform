"""Прогон методов краулера на сохранённой странице, без сети."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

from collector import Request, Response


async def run(method: Any, html: str, url: str, **metadata: Any) -> list[Any]:
    """Всё, что метод краулера отдаёт на странице ``html`` по адресу ``url``."""
    page = Response(
        SimpleNamespace(status_code=200, text=html), Request(url=url, metadata=metadata), method.__self__
    )
    return [out async for out in method(page)]
