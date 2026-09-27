"""Запуск площадок движка iTender (Fogsoft).

    uv run start_fogsoft [флаги run_all]
    uv run python -m tp.run_fogsoft --max-pages 2

Тот же ``run_all`` с теми же флагами, но только с площадками этого движка;
площадку другого движка он отклоняет как незнакомую.
"""

from __future__ import annotations

import run_all


def main(argv: list[str] | None = None) -> int:
    return run_all.main(argv, engine="fogsoft")


if __name__ == "__main__":
    raise SystemExit(main())
