"""План миграции ограничен полями типа, идемпотентен и защищён before."""

from core.trade_type import resolve_trade_type
from tp.scripts.trade_types import FIELDS, change, guard


def test_plan_preserves_original_and_ignores_unrelated_fields():
    document = {
        "_id": "id",
        "source": "ausib",
        "trade_type": None,
        "trade_number": "16539-ОТПП-К",
        "price": "100",
    }
    entry = change(document, {})
    assert entry["before"] == {"trade_type": None}
    assert set(entry["after"]) == set(FIELDS)
    assert entry["after"]["trade_kind"] == "публичное предложение"
    assert entry["after"]["trade_type_code"] == "ОТПП-К"
    assert guard(entry)["trade_type"] == {"$eq": None, "$exists": True}
    assert guard(entry)["trade_type_raw"] == {"$exists": False}
    assert "price" not in guard(entry)
    assert change({**document, **entry["after"]}, {}) is None


def test_explicit_independent_attributes():
    result = resolve_trade_type(
        {
            "Форма торга по составу участников": "Закрытая",
            "Форма представления предложений о цене": "Открытая",
        },
        {"trade_type": "Аукцион"},
    )
    assert result["trade_kind"] == "аукцион"
    assert result["trade_participation"] == "закрытая"
    assert result["trade_price_form"] == "открытая"
