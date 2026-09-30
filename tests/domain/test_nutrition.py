import pytest

from app.domain.food_db import load_food_db
from app.domain.nutrition import PlanItem, flatten_plan_items, item_macros, total_macros

DB = load_food_db()


def test_item_macros_scales_from_100g():
    item = PlanItem(food_key="riso_bianco_cotto", grams=200.0)
    m = item_macros(item, DB)
    food = DB["riso_bianco_cotto"]
    assert m.kcal == pytest.approx(food.kcal * 2)
    assert m.protein_g == pytest.approx(food.protein_g * 2)


def test_item_macros_half_portion():
    item = PlanItem(food_key="petto_di_pollo_cotto", grams=50.0)
    m = item_macros(item, DB)
    food = DB["petto_di_pollo_cotto"]
    assert m.protein_g == pytest.approx(food.protein_g * 0.5)


def test_item_macros_unknown_key_raises():
    item = PlanItem(food_key="does_not_exist", grams=100.0)
    with pytest.raises(KeyError):
        item_macros(item, DB)


def test_total_macros_sums_multiple_items():
    items = [
        PlanItem(food_key="riso_bianco_cotto", grams=100.0),
        PlanItem(food_key="petto_di_pollo_cotto", grams=150.0),
    ]
    totals = total_macros(items, DB)
    rice = DB["riso_bianco_cotto"]
    chicken = DB["petto_di_pollo_cotto"]
    assert totals.kcal == pytest.approx(rice.kcal + chicken.kcal * 1.5)
    assert totals.protein_g == pytest.approx(rice.protein_g + chicken.protein_g * 1.5)


def test_total_macros_empty_list():
    totals = total_macros([], DB)
    assert totals.kcal == 0
    assert totals.protein_g == 0


def test_flatten_plan_items_nested_structure():
    plan_dict = {
        "days": [
            {
                "meals": [
                    {"slot": "breakfast", "items": [{"food_key": "avena_fiocchi", "grams": 50, "note": ""}]},
                    {
                        "slot": "lunch",
                        "items": [
                            {"food_key": "riso_bianco_cotto", "grams": 150, "note": ""},
                            {"food_key": "petto_di_pollo_cotto", "grams": 120, "note": ""},
                        ],
                    },
                ]
            }
        ]
    }
    items = flatten_plan_items(plan_dict)
    assert len(items) == 3
    assert items[0] == PlanItem(food_key="avena_fiocchi", grams=50)
    assert items[2] == PlanItem(food_key="petto_di_pollo_cotto", grams=120)


def test_flatten_plan_items_multiple_days():
    plan_dict = {
        "days": [
            {"meals": [{"slot": "breakfast", "items": [{"food_key": "banana", "grams": 100, "note": ""}]}]},
            {"meals": [{"slot": "breakfast", "items": [{"food_key": "mela", "grams": 100, "note": ""}]}]},
        ]
    }
    items = flatten_plan_items(plan_dict)
    assert len(items) == 2


def test_flatten_plan_items_empty_plan():
    assert flatten_plan_items({"days": []}) == []
    assert flatten_plan_items({}) == []
