"""Массовый обход площадок Kendo-ETP по статусам.

    uv run python -m tp.run_kendo                          актуальные по умолчанию
    uv run python -m tp.run_kendo --status "Идет прием заявок"   названия через запятую
    uv run python -m tp.run_kendo --list                 площадки и статусы

Флаги — см. ``tp.runner``.
"""

from __future__ import annotations

from tp import runner
from tp.delete.kendo import ACTIVE, KNOWN_STATUSES
from tp.delete.kendo_platforms import PLATFORMS
from tp.delete.search import check_statuses


def main(argv: list[str] | None = None) -> int:
    return runner.main(
        argv,
        title="Kendo-ETP",
        platforms=PLATFORMS,
        default=ACTIVE,
        known=KNOWN_STATUSES,
        check=lambda value: ",".join(check_statuses(value, KNOWN_STATUSES)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
