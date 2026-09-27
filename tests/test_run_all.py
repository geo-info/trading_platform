"""Проверки сборки площадок: контракт модуля и то, что видны все площадки всех движков."""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest
from collector import Outcome, Stats
from collector.crawler.params import resolve_params

from core.settings import settings as config
from run_all import Result, build_parser, discover, finish, report, run_params
from tp.base import TenderFogsoft
from tp.btorg import TenderBtorg
from tp.common import CrawlParams
from tp.kendo import TenderKendo

#: Пакет площадок -> базовый класс движка и какие площадки в пакете ждём.
EXPECTED = {
    "fogsoft_platform": (
        TenderFogsoft,
        {
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
        },
    ),
    "kendo_platform": (TenderKendo, {"electro_torgi", "seltim", "torgi82", "trade_alliance", "vetp"}),
    "btorg_platform": (
        TenderBtorg,
        {"atctrade", "aukcioncenter", "ausib", "etp_profit", "ptp_center", "regtorg"},
    ),
}


def test_видны_все_площадки() -> None:
    assert {p.key for p in discover()} == set().union(*(keys for _, keys in EXPECTED.values()))


def test_у_каждой_площадки_свой_класс_и_стартовый_адрес() -> None:
    platforms = discover()
    assert len({p.parser_cls for p in platforms}) == len(platforms)
    assert len({p.parser_cls.start_urls[0] for p in platforms}) == len(platforms)


def test_площадки_наследуют_базовый_класс_своего_движка() -> None:
    for platform in discover():
        package = platform.module.__name__.split(".")[1]
        engine, keys = EXPECTED[package]
        cls = platform.parser_cls
        assert platform.key in keys and issubclass(cls, engine) and cls is not engine, platform.key
        # start_urls выводится из DOMAIN в __init_subclass__, а не пишется руками.
        assert cls.start_urls == [f"{cls.DOMAIN.rstrip('/')}/{cls.LISTING_PATH}"], platform.key


def test_площадка_переживает_отдельные_сбои_но_не_сломанную_вёрстку() -> None:
    """max_errors фреймворка по умолчанию 0: одна битая страница лота роняла бы площадку."""
    for platform in discover():
        assert platform.parser_cls.settings.max_errors == 50, platform.key


# ── параметры запуска ────────────────────────────────────────────────────────


def test_параметры_площадки_объявлены_с_умолчаниями_из_настроек() -> None:
    declared = TenderFogsoft.params
    assert isinstance(declared, CrawlParams)
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


# ── исход площадки ───────────────────────────────────────────────────────────


def outcome(stats: Stats | None, error: Exception | None = None) -> Outcome:
    crawl = None if stats is None else SimpleNamespace(stats=stats)
    return Outcome(crawler_cls=TenderFogsoft, crawl=crawl, error=error, elapsed=12.5)


def test_упавшая_площадка_сохраняет_статистику() -> None:
    """Раньше статистика упавшей площадки терялась вместе с исключением."""
    stats = Stats(requests=120, items=100, errors=51, duplicates=3, reason="max_errors")
    result = finish(Result(key="bep"), outcome(stats, TimeoutError("read timeout")))
    assert result.stats is stats  # статистика фреймворка, а не её копия
    assert result.failure == "TimeoutError: read timeout"
    assert (result.mark, result.ok) == ("ОШИБКА", False)


def test_прерванная_площадка_не_готова() -> None:
    result = finish(Result(key="bep"), outcome(Stats(items=5, reason="cancelled")))
    assert (result.mark, result.ok) == ("ПРЕРВАНО", False)


def test_площадка_упавшая_до_обхода() -> None:
    result = finish(Result(key="bep"), outcome(None, OSError("no TLS")))
    assert (result.stats.items, result.failure, result.ok) == (0, "OSError: no TLS", False)


def test_дошедшая_до_конца_площадка_готова() -> None:
    result = finish(Result(key="bep"), outcome(Stats(items=40, requests=42, reason="done")))
    assert (result.mark, result.ok, result.elapsed) == ("ГОТОВО", True, 12.5)
    assert report([result]) == 0
    assert report([result, finish(Result(key="etb"), outcome(Stats(reason="cancelled")))]) == 1
