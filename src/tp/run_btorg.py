"""Запуск площадок движка btorg (edoc-ETP).

    uv run start_btorg [флаги run_all]
    uv run python -m tp.run_btorg --max-pages 2

Тот же ``run_all`` с теми же флагами, но только с площадками этого движка;
площадку другого движка он отклоняет как незнакомую.
"""

from __future__ import annotations

import run_all


def main(argv: list[str] | None = None) -> int:
    return run_all.main(argv, engine="btorg")


if __name__ == "__main__":
    raise SystemExit(main())
