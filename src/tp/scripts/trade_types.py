"""Проверяемый план восстановления типов. plan не пишет в Mongo; apply — отдельно."""

from __future__ import annotations

import argparse
import http.cookiejar
import time
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from bson import json_util
from parsel import Selector
from pymongo import MongoClient

from core.conf import conf
from core.trade_type import detail_type_info, normalize_trade_type, resolve_trade_type
from tp.btorg.base import Btorg, parse_general
from tp.itender.detail import parse_detail
from tp.kendo.base import Kendo, parse_main_info
from tp.platforms import platforms
from tp.ruson.base import Ruson, field
from tp.scripts.common import select

FIELDS = tuple(normalize_trade_type(None))


def change(document: dict[str, Any], info: dict[str, str]) -> dict[str, Any] | None:
    """Только поля типа; before сохраняет также различие отсутствующего поля и null."""
    after = resolve_trade_type(info, document)
    if not after["trade_type_raw"] or all(document.get(k) == v and k in document for k, v in after.items()):
        return None
    return {
        "source": document["source"],
        "_id": document["_id"],
        "before": {k: document[k] for k in FIELDS if k in document},
        "after": after,
    }


def guard(entry: dict[str, Any]) -> dict[str, Any]:
    """Изменившийся после составления плана документ пропускается."""
    return {
        "_id": entry["_id"],
        "source": entry["source"],
        **{
            k: {"$eq": entry["before"][k], "$exists": True} if k in entry["before"] else {"$exists": False}
            for k in FIELDS
        },
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    plan = sub.add_parser("plan")
    plan.add_argument("names", nargs="*")
    plan.add_argument("--output", type=Path, required=True)
    plan.add_argument("--refresh-pages", action="store_true", help="GET страниц торгов; без записи деталей")
    plan.add_argument("--limit", type=int, default=0, help="на площадку; 0 — все документы")
    apply = sub.add_parser("apply")
    apply.add_argument("--plan", type=Path, required=True)
    args = parser.parse_args(argv)
    with MongoClient(conf.mongo.uri, serverSelectionTimeoutMS=5000) as client:
        db = client[conf.mongo.db]
        if args.action == "apply":
            changed = skipped = 0
            with args.plan.open(encoding="utf-8") as stream:
                for line in stream:
                    entry = json_util.loads(line)
                    if entry["source"] not in platforms() or set(entry["after"]) != set(FIELDS):
                        raise ValueError("план содержит посторонние поля или площадку")
                    result = db[entry["source"]].update_one(guard(entry), {"$set": entry["after"]})
                    changed += result.modified_count
                    skipped += not result.matched_count
            print(f"Обновлено: {changed}; не совпадает с before: {skipped}")
            return int(bool(skipped))
        if args.limit < 0:
            parser.error("--limit должен быть >= 0")
        chosen = select(args.names)
        opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        changed = errors = unresolved = 0
        # Не перезаписываем прежний план с резервными значениями.
        with args.output.open("x", encoding="utf-8") as output:
            for platform in chosen:
                cache: dict[str, dict[str, str] | Exception] = {}
                for document in db[platform.name].find({"source": platform.name}).limit(args.limit):
                    info = detail_type_info(document.get("detail") or {})
                    if args.refresh_pages:
                        url = (
                            document.get("lot_url")
                            if issubclass(platform, Btorg)
                            else document.get("trade_url") or document.get("lot_url")
                        )
                        if url not in cache:
                            try:
                                if not url or urlsplit(url).hostname != urlsplit(platform.DOMAIN).hostname:
                                    raise ValueError("URL не принадлежит площадке")
                                time.sleep(conf.parsing.delay)
                                with opener.open(url, timeout=conf.parsing.http_timeout) as response:
                                    encoding = response.headers.get_content_charset() or (
                                        "cp1251" if issubclass(platform, Btorg) else "utf-8"
                                    )
                                    page = Selector(response.read().decode(encoding))
                                if issubclass(platform, Btorg):
                                    page_info = parse_general(page)
                                elif issubclass(platform, Kendo):
                                    page_info = parse_main_info(page)
                                elif issubclass(platform, Ruson):
                                    page_info = {"Тип торгов": field(page, "Тип торгов")}
                                else:
                                    page_info = detail_type_info(parse_detail(page))
                                page_info = detail_type_info(page_info)
                                if not page_info:
                                    raise ValueError("на странице нет подписанного типа или номера торгов")
                                cache[url] = page_info
                            except Exception as exc:
                                cache[url] = exc
                        if isinstance(cache[url], Exception):
                            errors += 1
                            print(f"Ошибка {platform.name}/{document['lot_id']}: {cache[url]}")
                            continue
                        info = cache[url]
                    entry = change(document, info)
                    if entry:
                        output.write(json_util.dumps(entry, ensure_ascii=False) + "\n")
                        changed += 1
                    if not resolve_trade_type(info, document)["trade_kind"]:
                        unresolved += 1
        print(f"В плане: {changed}; неизвестный/пустой вид: {unresolved}; ошибки страниц: {errors}")
        return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
