"""Разбор страницы лота на сохранённых страницах площадок.

Фикстуры — настоящие страницы, снятые с площадок, а не выдуманная разметка:
все три дефекта ниже нашлись в данных, и воспроизвести их на синтетике значило
бы угадать, как именно вёрстка ломает разбор. Угадали бы — не нашли бы utender.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from parsel import Selector

from tp.source.fogsoft.marking.lot import parse_attachments, parse_detail, parse_price_schedule

FIXTURES = Path(__file__).parent / "fixtures"
LOT = "Информация о лоте"


def detail(name: str) -> dict:
    return parse_detail(Selector((FIXTURES / name).read_text(encoding="utf-8")))


# ── пары «подпись — значение» не съезжают ────────────────────────────────────


def test_распорка_без_подписи_не_сдвигает_значения_tendergarant() -> None:
    """Ячейка-распорка ``tdContent`` без своей подписи стоит перед «Начальной ценой»."""
    lot = detail("lot_tendergarant_19208.html")[LOT]
    assert lot["Начальная цена, руб."] == "533 293,04"
    assert lot["Шаг, % от начальной цены"] == "5,00"
    assert lot["Шаг, руб."] == "26 664,66"
    assert lot["Категория лота"] == "Жилых зданий"
    assert lot["Всего подано заявок на участие"] == "0"
    assert lot["Классификатор ЕФРСБ"] == ["[0401] Права долевой собственности"]
    assert lot[
        "Порядок оформления участия в торгах, перечень представляемых заявителями документов и требования к их оформлению"
    ].startswith("Для участия в торгах")


def test_распорка_с_colspan_не_сдвигает_значения_utender() -> None:
    lot = detail("lot_utender_767399.html")[LOT]
    assert lot[
        "Сведения об имуществе должника, его составе, характеристиках, описание, порядок ознакомления"
    ].startswith("Разбавитель")
    assert lot["Классификатор ЕФРСБ"] == ["Прочее"]
    assert lot["Категория лота"] == "Не определена"


@pytest.mark.parametrize(
    "name", ["lot_tendergarant_19208.html", "lot_utender_767399.html", "lot_centerr_1170194.html"]
)
def test_пустых_подписей_в_разделах_нет(name: str) -> None:
    for section, pairs in detail(name).items():
        assert all(pairs), f"{section}: пустая подпись в {list(pairs)}"


# ── форма загрузки документа — не раздел лота ────────────────────────────────


@pytest.mark.parametrize("name", ["lot_tendergarant_19208.html", "lot_centerr_1170194.html"])
def test_форма_загрузки_документа_отбрасывается(name: str) -> None:
    assert "Информация о документе" not in detail(name)


# ── классификатор ЕФРСБ — список классов, а не склеенная строка ──────────────


def test_несколько_классов_ефрсб_остаются_раздельными() -> None:
    lot = detail("lot_centerr_1170194.html")[LOT]
    assert lot["Классификатор ЕФРСБ"] == [
        "Здания (кроме жилых) и сооружения, не включенные в другие группировки",
        "Земельные участки",
    ]


def test_цена_centerr_без_рекламной_кнопки() -> None:
    lot = detail("lot_centerr_1170194.html")[LOT]
    assert lot["Текущая цена, руб."] == "653 937,07"
    assert lot["Начальная цена, руб."] == "653 937,07"


# ── документы и график снижения цены ────────────────────────────────────────


def test_документы_лота() -> None:
    attachments = parse_attachments(
        Selector((FIXTURES / "lot_tendergarant_19208.html").read_text(encoding="utf-8"))
    )
    assert attachments
    assert all(a["url"] and a["name"] for a in attachments)
    assert all(isinstance(a["signed"], bool) for a in attachments)


def test_график_снижения_цены_только_у_публичного_предложения() -> None:
    schedule = parse_price_schedule(
        Selector((FIXTURES / "lot_centerr_1170194.html").read_text(encoding="utf-8"))
    )
    assert schedule and all(len(row) > 1 for row in schedule)
    assert (
        parse_price_schedule(Selector((FIXTURES / "lot_tendergarant_19208.html").read_text(encoding="utf-8")))
        == []
    )
