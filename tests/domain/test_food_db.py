import json

import pytest

from app.domain.food_db import FoodDbError, filter_foods, load_food_db


def test_real_food_db_loads_without_error():
    db = load_food_db()
    assert len(db) >= 60
    assert "riso_bianco_cotto" in db
    assert "petto_di_pollo_cotto" in db


def test_every_row_satisfies_atwater_identity():
    db = load_food_db()
    for key, food in db.items():
        recomputed = 4 * food.protein_g + 4 * food.carb_g + 9 * food.fat_g
        assert recomputed == pytest.approx(food.kcal, rel=0.10), key


def test_no_duplicate_keys_in_real_db():
    with open("data/foods/foods.it.json", encoding="utf-8") as f:
        rows = json.load(f)
    keys = [r["key"] for r in rows]
    assert len(keys) == len(set(keys))


def test_rejects_row_with_bad_atwater_math(tmp_path):
    bad_db = tmp_path / "bad.json"
    bad_db.write_text(
        json.dumps(
            [
                {
                    "key": "broken",
                    "name_it": "x",
                    "name_en": "x",
                    "per_100g": {"kcal": 999, "protein_g": 1, "carb_g": 1, "fat_g": 1, "fiber_g": 0},
                    "tags": [],
                }
            ]
        )
    )
    with pytest.raises(FoodDbError, match="Atwater"):
        load_food_db(bad_db)


def test_rejects_duplicate_key(tmp_path):
    row = {
        "key": "dup",
        "name_it": "x",
        "name_en": "x",
        "per_100g": {"kcal": 40, "protein_g": 10, "carb_g": 0, "fat_g": 0, "fiber_g": 0},
        "tags": [],
    }
    bad_db = tmp_path / "dup.json"
    bad_db.write_text(json.dumps([row, row]))
    with pytest.raises(FoodDbError, match="duplicate"):
        load_food_db(bad_db)


def test_rejects_missing_field(tmp_path):
    bad_db = tmp_path / "missing.json"
    bad_db.write_text(
        json.dumps(
            [
                {
                    "key": "incomplete",
                    "name_it": "x",
                    "name_en": "x",
                    "per_100g": {"kcal": 40, "protein_g": 10, "carb_g": 0, "fat_g": 0},
                    "tags": [],
                }
            ]
        )
    )
    with pytest.raises(FoodDbError, match="missing fields"):
        load_food_db(bad_db)


def test_rejects_non_positive_kcal(tmp_path):
    bad_db = tmp_path / "zero.json"
    bad_db.write_text(
        json.dumps(
            [
                {
                    "key": "zero_kcal",
                    "name_it": "x",
                    "name_en": "x",
                    "per_100g": {"kcal": 0, "protein_g": 0, "carb_g": 0, "fat_g": 0, "fiber_g": 0},
                    "tags": [],
                }
            ]
        )
    )
    with pytest.raises(FoodDbError, match="non-positive"):
        load_food_db(bad_db)


def test_filter_excludes_allergen_tags():
    db = load_food_db()
    filtered = filter_foods(db, exclude_tags=("fish",))
    assert "salmone_cotto" not in filtered
    assert "petto_di_pollo_cotto" in filtered


def test_filter_requires_all_diet_tags():
    db = load_food_db()
    vegan = filter_foods(db, require_tags=("vegan",))
    assert "tofu" in vegan
    assert "petto_di_pollo_cotto" not in vegan
    assert "mozzarella" not in vegan  # vegetarian but not vegan


def test_filter_combines_exclude_and_require():
    db = load_food_db()
    filtered = filter_foods(db, exclude_tags=("nuts",), require_tags=("vegan", "gluten_free"))
    assert "mandorle" not in filtered  # vegan+gluten_free but has nuts
    assert "riso_bianco_cotto" in filtered


def test_name_locale_selection():
    db = load_food_db()
    banana = db["banana"]
    assert banana.name("it") == "Banana"
    assert banana.name("en") == "Banana"
    pasta = db["pasta_cotta"]
    assert pasta.name("it") == "Pasta di semola (cotta)"
    assert pasta.name("en") == "Pasta (cooked)"
