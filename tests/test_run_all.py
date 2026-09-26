"""Проверки сборки площадок: контракт модуля и то, что все шестнадцать видны."""

from __future__ import annotations

import inspect
from datetime import date

import pytest
from collector.crawler.params import resolve_params

from core.settings import settings as config
from tp.base import FogsoftParams, TenderFogsoft, crawl
from tp.platform.run_all import build_parser, discover, run_params

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


def test_площадка_переживает_отдельные_сбои_но_не_сломанную_вёрстку() -> None:
    """max_errors фреймворка по умолчанию 0: одна битая страница лота роняла бы площадку."""
    for platform in discover():
        assert platform.parser_cls.settings.max_errors == 50, platform.key


# ── параметры запуска ────────────────────────────────────────────────────────


def test_параметры_площадки_объявлены_с_умолчаниями_из_настроек() -> None:
    declared = TenderFogsoft.params
    assert isinstance(declared, FogsoftParams)
    assert (declared.max_pages, declared.since) == (config.max_pages, config.since)
    # Предел и окно больше не атрибуты класса, которые run_all переписывал.
    assert not hasattr(TenderFogsoft, "MAX_PAGES") and not hasattr(TenderFogsoft, "SINCE")


def test_строки_запуска_приводятся_к_типам_параметров() -> None:
    for platform in discover():
        run = resolve_params(platform.parser_cls.params, {"max_pages": "2", "since": "2026-06-01"})
        assert (run.max_pages, run.since) == (2, date(2026, 6, 1)), platform.key
    with pytest.raises(ValueError, match="max_page"):
        resolve_params(TenderFogsoft.params, {"max_page": "2"})


def test_run_all_передаёт_только_заданные_параметры() -> None:
    args = build_parser().parse_args(["--max-pages", "2", "--since", "2026-06-01", "--max-errors", "5"])
    assert run_params(args) == {"max_pages": 2, "since": date(2026, 6, 1), "max_errors": 5}
    assert run_params(build_parser().parse_args(["centerr"])) == {}
