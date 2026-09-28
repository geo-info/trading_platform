"""Массовый обход площадок rus-on по статусам.

    uv run python -m tp.run_ruson                          актуальные по умолчанию
    uv run python -m tp.run_ruson --status "Прием заявок"   названия через запятую
    uv run python -m tp.run_ruson --list                 площадки и статусы

Флаги — см. ``tp.runner``.
"""

from __future__ import annotations

from tp import runner
from tp.delete.ruson import ACTIVE, KNOWN_STATUSES
from tp.delete.ruson_platforms import PLATFORMS
from tp.delete.search import check_statuses


def main(argv: list[str] | None = None) -> int:
    return runner.main(
        argv,
        title="rus-on",
        platforms=PLATFORMS,
        default=ACTIVE,
        known=KNOWN_STATUSES,
        check=lambda value: ",".join(check_statuses(value, KNOWN_STATUSES)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
