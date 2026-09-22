"""Проверки сборки площадок: контракт модуля и то, что все шестнадцать видны."""

from __future__ import annotations

import inspect

from tp.base import TenderFogsoft, crawl
from tp.platform.run_all import discover

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


def test_обход_асинхронный_и_общий_на_все_площадки() -> None:
    """crawl() переехал в базу и принимает класс площадки, а не живёт в каждом модуле."""
    assert inspect.iscoroutinefunction(crawl)
    assert list(inspect.signature(crawl).parameters) == ["parser_cls"]


def test_площадки_наследуют_базовый_класс() -> None:
    for platform in discover():
        cls = platform.parser_cls
        assert issubclass(cls, TenderFogsoft) and cls is not TenderFogsoft, platform.key
        # start_urls выводится из DOMAIN в __init_subclass__, а не пишется руками.
        assert cls.start_urls == [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"], platform.key
