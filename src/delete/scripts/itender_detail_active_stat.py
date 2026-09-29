"""Сколько актуальных лотов iTender ещё ждут деталей — только чтение базы.

    uv run python -m tp.scripts.itender_detail_active_stat                    все площадки
    uv run python -m tp.scripts.itender_detail_active_stat alfalot centerr    только эти

Та же таблица, что ``tp.scripts.itender_detail_stat``, но только по актуальным лотам —
тем же статусам, что берёт ``tp.scripts.itender_detail_active_run``.
"""

from __future__ import annotations

import asyncio
import sys

from tp.scripts.itender_detail_active_run import ACTIVE
from tp.scripts.itender_detail_stat import stat


def main() -> None:
    asyncio.run(stat(sys.argv[1:], ACTIVE))


if __name__ == '__main__':
    main()
