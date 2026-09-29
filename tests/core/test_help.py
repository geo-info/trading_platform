"""Разбор значений площадок: пробелы, цена, дата по Москве, ссылки без схемы."""

from __future__ import annotations

from datetime import datetime

import pytest

from core.help import MSK, clean, digits, local_href, parse_datetime, parse_price


def test_clean_схлопывает_пробелы_и_nbsp() -> None:
    assert clean("  a\xa0 b\n c ") == "a b c"
    assert clean("   ") is None
    assert clean(None) is None


def test_digits_ведущие_цифры() -> None:
    assert digits("10840–ОАОФ") == "10840"
    assert digits("ОАОФ") == ""
    assert digits(None) == ""


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("http://trade-alliance.ru/lots?page=2", "/lots?page=2"),
        ("https://x.ru/a/b", "/a/b"),
        ("//x.ru/a?b=1", "/a?b=1"),
        ("https://x.ru", "/"),
        ("list.html?page=3", "list.html?page=3"),
        ("/lots?page=4", "/lots?page=4"),
    ],
)
def test_local_href_отрезает_схему_и_хост(href: str, expected: str) -> None:
    assert local_href(href) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("1 234 567,89", 1234567.89),
        ("1 315 000.00", 1315000.0),
        ("280 000,00 руб, НДС не облагается", 280000.0),
        ("1\xa0000,50", 1000.5),
        ("0,00", 0.0),
        ("Купить с агентом", None),
        ("", None),
        (None, None),
        ("12.5.3", None),
    ],
)
def test_parse_price(raw: str | None, expected: float | None) -> None:
    assert parse_price(raw) == expected


def test_parse_datetime_по_москве() -> None:
    assert parse_datetime("28.10.2026 10:00 (34 дн.)") == datetime(2026, 10, 28, 10, 0, tzinfo=MSK)
    assert parse_datetime("28.10.2026 10:00:30") == datetime(2026, 10, 28, 10, 0, 30, tzinfo=MSK)
    assert parse_datetime("10.09.2026") == datetime(2026, 9, 10, tzinfo=MSK)
    assert parse_datetime("28.10.2026 10:00").utcoffset().total_seconds() == 3 * 3600


@pytest.mark.parametrize("raw", ["когда-нибудь", "31.02.2026", "28.10.2026 25:00", "", None])
def test_parse_datetime_невалидное_это_none(raw: str | None) -> None:
    assert parse_datetime(raw) is None
