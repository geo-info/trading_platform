"""Массовый обход площадок iTender (Fogsoft) по статусам.

    uv run python -m tp.run_fogsoft                          актуальные: 5, 7, 14
    uv run python -m tp.run_fogsoft --status "Прием заявок"   код или название, можно через запятую
    uv run python -m tp.run_fogsoft --status 7 --max-pages 2 centerr bep
    uv run python -m tp.run_fogsoft --list                 площадки и статусы

Флаги — см. ``tp.runner``.
"""

from __future__ import annotations

from tp import runner
from tp.delete.fogsoft import ACTIVE, STATUSES, resolve_statuses
from tp.delete.fogsoft_platforms import PLATFORMS


def main(argv: list[str] | None = None) -> int:
    return runner.main(
        argv,
        title="iTender (Fogsoft)",
        platforms=PLATFORMS,
        default=ACTIVE,
        known=[f"{code} — {name}" for code, name in STATUSES.items()],
        check=lambda value: ",".join(resolve_statuses(value)),
    )


if __name__ == "__main__":
    raise SystemExit(main())
