"""Удалить базу лотов в Mongo целиком — начать сбор с чистого листа.

    uv run python -m tp.scripts.drop_db          покажет, что удалится, и спросит
    uv run python -m tp.scripts.drop_db --yes    без вопроса

База и адрес — из настроек (``MONGO_URI``, ``MONGO_DB``; по умолчанию
``trading`` на локальной Mongo). Удаление необратимо. Индексы заводить заново
не нужно: хранилище создаёт их само при первом открытии.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from collections.abc import Sequence
from typing import Any

from pymongo.errors import PyMongoError

from core.conf import conf
from core.db.mongo.client import create_client


async def contents(client: Any, db_name: str) -> dict[str, int]:
    """Коллекции базы и число документов в каждой; пустой словарь — базы нет."""
    db = client[db_name]
    return {name: await db[name].estimated_document_count() for name in sorted(await db.list_collection_names())}


async def drop(client: Any, db_name: str, *, confirm: bool) -> int:
    """Показать содержимое базы и удалить её; ``confirm`` — спросить перед удалением."""
    found = await contents(client, db_name)
    if not found:
        print(f"базы {db_name} нет — удалять нечего")
        return 0
    print(f"база {db_name} на {conf.mongo.uri}:")
    for name, count in found.items():
        print(f"  {name:24} {count:>8}")
    print(f"  {'всего документов':24} {sum(found.values()):>8}")
    if confirm and input(f"\nудалить базу {db_name} целиком? введите её имя для подтверждения: ").strip() != db_name:
        print("отменено")
        return 1
    await client.drop_database(db_name)
    print(f"база {db_name} удалена")
    return 0


async def run(db_name: str, *, confirm: bool) -> int:
    client = create_client()
    try:
        return await drop(client, db_name, confirm=confirm)
    finally:
        await client.close()


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=f"Удалить базу лотов {conf.mongo.db} в Mongo целиком.")
    ap.add_argument("--yes", action="store_true", help="не спрашивать подтверждение")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    try:
        return asyncio.run(run(conf.mongo.db, confirm=not args.yes))
    except PyMongoError as exc:
        print(f"Mongo недоступна ({conf.mongo.uri}): {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
