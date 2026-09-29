"""Массовый обход площадок btorg (edoc-ETP) по статусам.

    uv run python -m tp.run_btorg                          актуальные по умолчанию
    uv run python -m tp.run_btorg --status "идёт приём заявок"   названия через запятую
    uv run python -m tp.run_btorg --list                 площадки и статусы

Флаги — см. ``tp.runner``.
"""

from __future__ import annotations

from tp import runner
from tp.delete.btorg import ACTIVE, KNOWN_STATUSES
from tp.delete.btorg_platforms import PLATFORMS
from tp.delete.search import check_statuses


def main(argv: list[str] | None = None) -> int:
    return runner.main(
        argv,
        title="btorg (edoc-ETP)",
        platforms=PLATFORMS,
        default=ACTIVE,
        known=KNOWN_STATUSES,
        check=lambda value: ",".join(check_statuses(value, KNOWN_STATUSES)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
