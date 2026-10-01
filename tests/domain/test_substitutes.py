import pytest

from app.domain.food_db import load_food_db
from app.domain.substitutes import find_substitutes

DB = load_food_db()


def test_chicken_substitute_is_another_lean_protein():
    results = find_substitutes("petto_di_pollo_cotto", DB, n=3)
    keys = [r.food.key for r in results]
    # Turkey breast is the closest macro match to chicken breast in this DB.
    assert "petto_di_tacchino_cotto" in keys


def test_results_are_sorted_by_distance_ascending():
    results = find_substitutes("petto_di_pollo_cotto", DB, n=5)
    distances = [r.distance for r in results]
    assert distances == sorted(distances)


def test_target_food_never_appears_in_its_own_substitutes():
    results = find_substitutes("riso_bianco_cotto", DB, n=10)
    assert all(r.food.key != "riso_bianco_cotto" for r in results)


def test_respects_n_limit():
    results = find_substitutes("banana", DB, n=2)
    assert len(results) == 2


def test_excludes_allergen_tags():
    results = find_substitutes("merluzzo_cotto", DB, exclude_tags=("fish",), n=10)
    assert all("fish" not in r.food.tags for r in results)


def test_requires_diet_tags():
    results = find_substitutes("petto_di_pollo_cotto", DB, require_tags=("vegan",), n=10)
    assert all("vegan" in r.food.tags for r in results)


def test_unknown_food_key_returns_empty_list():
    assert find_substitutes("does_not_exist", DB) == []


def test_rice_substitute_is_a_similar_starch_not_a_vegetable():
    results = find_substitutes("riso_bianco_cotto", DB, n=3)
    keys = [r.food.key for r in results]
    starches = {"pasta_cotta", "riso_integrale_cotto", "couscous_cotto", "orzo_cotto", "farro_cotto", "pane_bianco", "pane_integrale"}
    assert any(k in starches for k in keys)


def test_vegan_requirement_excludes_dairy_and_meat_from_cheese_substitutes():
    results = find_substitutes("mozzarella", DB, require_tags=("vegan",), n=10)
    assert all("vegan" in r.food.tags for r in results)
    assert "petto_di_pollo_cotto" not in [r.food.key for r in results]
