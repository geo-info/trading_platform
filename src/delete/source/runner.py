"""Массовый обход площадок одного движка по статусам — общее для скриптов ``run_*``.

Скрипт движка (``tp.run_fogsoft``, ``tp.run_kendo`` …) передаёт сюда свои
площадки, статусы по умолчанию и проверку статусов, а здесь — разбор
командной строки, параллельный обход ``crawl_many`` и итоговая таблица.

Площадки обходятся параллельно — серверы разные и друг другу не мешают, —
лоты пишутся в Mongo (``core.db``) под именем площадки. Статусы проверяются до
старта: опечатка в названии не превращается в пустые обходы всех площадок.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import time
from collections.abc import Callable
from typing import Any

from collector import Crawl, Crawler, crawl_many

from core.db import MongoStore
from core.db.mongo import create_client, new_run_id
from core.conf import settings as config


async def run(
    platforms: dict[str, type[Crawler]], names: list[str], params: dict[str, Any]
) -> dict[str, dict[str, Any]]:
    """Обойти площадки ``names``; итог по каждой — лоты, новые, запросы, ошибки, причина."""
    clock = time.monotonic()
    run_id = new_run_id()
    results: dict[str, dict[str, Any]] = {name: {"items": 0, "new": 0} for name in names}
    client = create_client()

    async def consume(crawl: Crawl) -> None:
        result = results[crawl.crawler.name]
        async with MongoStore(crawl.crawler.name, client=client, run_id=run_id) as store:
            async for item in crawl.stream():
                result["items"] += 1
                result["new"] += await store.upsert(item)

    async def log(name: str, message: str) -> None:
        print(f"[{time.monotonic() - clock:6.1f}с] {name:15} {message}", flush=True)

    print(f"площадок {len(names)}, статусы {params['statuses']}, run_id {run_id}\n", flush=True)
    try:
        async for outcome in crawl_many(
            [platforms[name] for name in names],
            concurrency=config.parsing.platform_concurrency,
            params=params,
            consume=consume,
            log=log,
        ):
            result = results[outcome.crawler_cls.name]
            stats = outcome.crawl.stats if outcome.crawl else None
            result.update(
                requests=stats.requests if stats else 0,
                errors=stats.errors if stats else 0,
                reason=stats.reason if stats else "",
                failure=f"{type(outcome.error).__name__}: {outcome.error}" if outcome.error else "",
                elapsed=outcome.elapsed,
            )
    finally:
        await client.close()
    return results


def report(results: dict[str, dict[str, Any]]) -> int:
    """Итоговая таблица; код выхода не ноль, если какая-то площадка упала."""
    print(f"\n{'площадка':15} {'лотов':>6} {'новых':>6} {'запр':>5} {'ош':>3} {'время':>7}  причина")
    for name, r in sorted(results.items(), key=lambda kv: -kv[1]["items"]):
        why = r["failure"][:60] or r["reason"]
        print(
            f"{name:15} {r['items']:>6} {r['new']:>6} {r['requests']:>5} {r['errors']:>3} {r['elapsed']:6.1f}с  {why}"
        )
    failed = [name for name, r in results.items() if r["failure"]]
    total = sum(r["items"] for r in results.values())
    print(f"\nитого лотов {total}, площадок {len(results) - len(failed)} из {len(results)}")
    print(f"хранилище: {config.mongo.uri}/{config.mongo.db}.{config.mongo.collection}")
    return 1 if failed else 0


def main(
    argv: list[str] | None,
    *,
    title: str,
    platforms: dict[str, type[Crawler]],
    default: str,
    known: list[str],
    check: Callable[[str], str],
) -> int:
    """Запуск из командной строки.

    ``default`` — статусы прогона по умолчанию, ``known`` — что показать в
    ``--list``, ``check`` — статусы из ``--status`` в значение параметра
    ``statuses`` или ``ValueError``, если какой-то незнаком.
    """
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    ap = argparse.ArgumentParser(description=f"Массовый обход площадок {title} по статусам.")
    ap.add_argument("platforms", nargs="*", help="какие площадки; по умолчанию все")
    ap.add_argument("--status", default=default, help=f"статусы через запятую; по умолчанию «{default}»")
    ap.add_argument("--max-pages", type=int, metavar="N", help="предел страниц выдачи на статус")
    ap.add_argument("--list", action="store_true", help="показать площадки и статусы и выйти")
    ap.add_argument("-v", "--verbose", action="store_true", help="логи самого фреймворка")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING, format="%(message)s")

    if args.list:
        print("площадки:", ", ".join(sorted(platforms)))
        print("статусы:", "; ".join(known))
        return 0
    try:
        statuses = check(args.status)
    except ValueError as exc:
        print(exc, file=sys.stderr)
        return 2
    if unknown := [name for name in args.platforms if name not in platforms]:
        print(
            f"незнакомые площадки: {', '.join(unknown)}; известные: {', '.join(sorted(platforms))}",
            file=sys.stderr,
        )
        return 2

    params: dict[str, Any] = {"statuses": statuses}
    if args.max_pages is not None:
        params["max_pages"] = args.max_pages
    results = asyncio.run(run(platforms, args.platforms or sorted(platforms), params))
    return report(results)
