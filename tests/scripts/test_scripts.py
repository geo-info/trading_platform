"""Скрипты запуска: выбор площадок, детальный парсер по движку, параллельный прогон, итог, аргументы."""

from __future__ import annotations

import pytest

from tp.btorg.detail import BtorgDetail
from tp.itender.detail import ITenderDetail
from tp.kendo.detail import KendoDetail
from tp.platforms import platforms
from tp.ruson.detail import RusonDetail
from tp.scripts import crawl, detail
from tp.scripts.common import ENGINES, Result, detail_of, report, run_many, select


def test_без_имён_все_площадки() -> None:
    assert len(select([])) == 32


def test_движок_и_площадка_вперемешку() -> None:
    names = [p.name for p in select(["kendo", "atctrade"])]
    assert sorted(names) == sorted([*platforms(ENGINES["kendo"]), "atctrade"])


def test_повтор_не_дублирует() -> None:
    assert [p.name for p in select(["kendo", "seltim"])].count("seltim") == 1


def test_незнакомое_имя_ошибка() -> None:
    with pytest.raises(ValueError, match="нет площадок или движков: nope"):
        select(["kendo", "nope"])


@pytest.mark.parametrize(
    ("name", "mixin"),
    [("centerr", ITenderDetail), ("seltim", KendoDetail), ("atctrade", BtorgDetail), ("rus_on", RusonDetail)],
)
def test_детальный_парсер_по_движку(name: str, mixin: type) -> None:
    platform = platforms()[name]
    d = detail_of(platform)
    assert issubclass(d, mixin) and issubclass(d, platform)
    assert d.name == name


def test_детальный_парсер_есть_у_каждой_площадки() -> None:
    for platform in select([]):
        assert detail_of(platform).name == platform.name


async def test_упавшая_площадка_не_останавливает_остальные() -> None:
    chosen = select(["seltim", "atctrade"])

    async def one(platform: type) -> Result:
        if platform.name == "seltim":
            raise RuntimeError("сеть")
        return Result(platform.name, done=3, new=1)

    results = {r.name: r for r in await run_many(chosen, one, concurrency=1)}
    assert results["seltim"].failure == "RuntimeError: сеть"
    assert (results["atctrade"].done, results["atctrade"].failure) == (3, "")


def test_код_выхода(capsys: pytest.CaptureFixture[str]) -> None:
    assert report([Result("a", done=2)], "лотов", "новых") == 0
    assert report([Result("a", done=2), Result("b", failure="X: y")], "лотов", "новых") == 1
    out = capsys.readouterr().out
    assert "упали: b" in out


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    assert crawl.main(["--list"]) == 0
    assert "kendo: trade_alliance" in capsys.readouterr().out


@pytest.mark.parametrize("script", [crawl, detail])
def test_незнакомая_площадка_код_2(script, capsys: pytest.CaptureFixture[str]) -> None:
    assert script.main(["nope"]) == 2
    assert "nope" in capsys.readouterr().err


def test_умолчания() -> None:
    assert crawl.MAX_PAGES == 30
    assert detail.LIMIT == 100
