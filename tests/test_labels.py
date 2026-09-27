"""Сведение подписей страницы лота к одному написанию.

Фикстуры — настоящие страницы, на которых разведка нашла расхождения:
etpu_bankrupt с «(Московское время)», tendergarant с «Обеспечением задатка»,
латинской «p» в «pуб.», отказом победителя и пробелом перед двоеточием,
utender с «Заключением договора».
"""

from __future__ import annotations

from pathlib import Path

from parsel import Selector

from tp.marking.fogsoft import parse_detail, raw_detail
from tp.marking.fogsoft_labels import canon_detail, canon_label

FIXTURES = Path(__file__).parent / "fixtures"
LOT = "Информация о лоте"
DEPOSIT = "Обеспечение заявки"
CONTRACT = "Информация о договоре купли-продажи"


def page(name: str) -> Selector:
    return Selector((FIXTURES / name).read_text(encoding="utf-8"))


def labels(detail: dict) -> set[str]:
    return {label for pairs in detail.values() for label in pairs}


def test_московское_время_срезается_etpu_bankrupt() -> None:
    lot = parse_detail(page("etpu_bankrupt_lot_138856.html"))[LOT]
    assert {"Дата проведения", "Дата начала представления заявок на участие"} <= set(lot)
    assert not any("Московское время" in label for label in lot)


def test_обеспечение_задатка_сводится_к_обеспечению_заявки() -> None:
    for name in ("tendergarant_lot_19055.html", "utender_lot_766294.html"):
        detail = parse_detail(page(name))
        assert "Обеспечение задатка" not in detail
        assert {"Дата внесения обеспечения", "Порядок внесения и возврата обеспечения"} <= set(
            detail[DEPOSIT]
        )
        assert not any("задатк" in label for label in detail[DEPOSIT]), name


def test_заключение_договора_сводится_к_информации_о_договоре_utender() -> None:
    detail = parse_detail(page("utender_lot_766294.html"))
    assert "Заключение договора купли-продажи" not in detail
    assert set(detail[CONTRACT]) == {"Дата заключения договора", "Договор заключен с"}
    assert (
        "Порядок оформления участия в торгах, перечень представляемых заявителями документов "
        "и требования к их оформлению" in detail[LOT]
    )


def test_латинская_p_в_цене_договора() -> None:
    contract = parse_detail(page("tendergarant_lot_19055.html"))[CONTRACT]
    assert "Цена договора, руб." in contract
    assert "Цена договора, pуб." not in contract


def test_пробел_перед_двоеточием_не_остаётся_в_подписи() -> None:
    """«Тип снижения цены публичного предложения :» — без strip ключ двоился."""
    lot = raw_detail(page("tendergarant_lot_19055.html"))[LOT]
    assert "Тип снижения цены публичного предложения" in lot
    assert all(label == label.strip() for label in lot)


def test_причина_отказа_выносится_из_раздела_в_список() -> None:
    detail, refusals = canon_detail(raw_detail(page("tendergarant_lot_19055.html")))
    assert refusals == [{"role": "победителя", "party": "ИП Рузанов Глеб Юрьевич", "reason": "-"}]
    assert not any(label.startswith("Причина отказа") for label in labels(detail))


def test_отказ_участника_с_местом() -> None:
    detail = {CONTRACT: {'Причина отказа участника, занявшего 2 место (ООО "Ромашка")': "Отказ"}}
    sections, refusals = canon_detail(detail)
    assert refusals == [{"role": "участника", "party": 'ООО "Ромашка"', "reason": "Отказ", "place": 2}]
    assert sections == {}  # раздел из одних отказов пустым не остаётся


def test_три_написания_даты_публикации() -> None:
    target = "Дата публикации в печатном органе по месту нахождения должника"
    for label in (
        "Дата публикации в печатном органе по месту нахождения",
        "Дата публикации в печатном органе по месту нахождения должника",
        "Дата публикации в печатном органе по месту нахождения должника или иных СМИ",
    ):
        assert canon_label(label) == target


def test_при_двух_написаниях_остаётся_непустое() -> None:
    detail = {
        DEPOSIT: {"Размер обеспечения, руб.": None},
        "Обеспечение задатка": {"Размер задатка, руб.": "10,00"},
    }
    assert canon_detail(detail)[0] == {DEPOSIT: {"Размер обеспечения, руб.": "10,00"}}
