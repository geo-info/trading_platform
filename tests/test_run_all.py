"""Проверки сборки площадок: контракт модуля и то, что все шестнадцать видны."""

from __future__ import annotations

import inspect

from trading.run_all import discover

EXPECTED = {
    "alfalot",
    "arbbitlot",
    "arbitat",
    "bep",
    "centerr",
    "etb",
    "etpu_bankrupt",
    "etpugra",
    "gloria_service",
    "meta_invest",
    "tender_one",
    "tendergarant",
    "utender",
    "utp_lot",
    "yuzhnyy_etp",
    "zakazrf",
}


def test_видны_все_площадки() -> None:
    assert {p.key for p in discover()} == EXPECTED


def test_у_каждой_площадки_свой_класс_и_стартовый_адрес() -> None:
    platforms = discover()
    assert len({p.parser_cls for p in platforms}) == len(platforms)
    assert len({p.parser_cls.start_urls[0] for p in platforms}) == len(platforms)


def test_парсеры_пишут_асинхронно() -> None:
    """crawl() каждой площадки — корутина и больше не принимает хранилище извне."""
    for platform in discover():
        crawl = platform.module.crawl
        assert inspect.iscoroutinefunction(crawl), platform.key
        assert not inspect.signature(crawl).parameters, platform.key
