import pytest

from app.domain.food_db import load_food_db
from app.domain.models import MacroTargets
from app.domain.nutrition import flatten_plan_items, total_macros
from app.llm.validator import validate

DB = load_food_db()


def _plan(*meals_items):
    """meals_items: list of (slot, [(food_key, grams), ...])"""
    return {
        "days": [
            {
                "meals": [
                    {
                        "slot": slot,
                        "items": [{"food_key": k, "grams": g, "note": ""} for k, g in items],
                    }
                    for slot, items in meals_items
                ]
            }
        ]
    }


def target_macros_from_plan(plan_dict):
    items = flatten_plan_items(plan_dict)
    totals = total_macros(items, DB)
    return totals.kcal, MacroTargets(
        protein_g=totals.protein_g,
        carb_g=totals.carb_g,
        fat_g=totals.fat_g,
        fiber_g=totals.fiber_g,
        kcal_from_macros=totals.kcal,
    )


def test_passing_plan_within_tolerance():
    plan = _plan(
        ("breakfast", [("avena_fiocchi", 60), ("banana", 100)]),
        ("lunch", [("riso_bianco_cotto", 250), ("petto_di_pollo_cotto", 200), ("olio_oliva", 10)]),
        ("dinner", [("merluzzo_cotto", 180), ("broccoli_cotti", 200)]),
    )
    target_kcal, macros = target_macros_from_plan(plan)
    result = validate(plan, target_kcal, macros, DB)
    assert result.ok
    assert not result.hard_failed


def test_kcal_too_high_fails_tolerance_not_hard_fail():
    plan = _plan(("lunch", [("riso_bianco_cotto", 300), ("olio_oliva", 30)]))
    target_kcal, macros = target_macros_from_plan(plan)
    # Now double the actual portions so kcal massively overshoots the
    # target that was derived from the original (smaller) plan.
    bloated = _plan(("lunch", [("riso_bianco_cotto", 600), ("olio_oliva", 60)]))
    result = validate(bloated, target_kcal, macros, DB)
    assert result.hard_failed is False
    assert result.ok is False
    assert result.tolerance.kcal_ok is False


def test_protein_too_low_fails_tolerance():
    plan = _plan(("lunch", [("petto_di_pollo_cotto", 200), ("riso_bianco_cotto", 200)]))
    target_kcal, macros = target_macros_from_plan(plan)
    low_protein = _plan(("lunch", [("petto_di_pollo_cotto", 50), ("riso_bianco_cotto", 200)]))
    result = validate(low_protein, target_kcal, macros, DB)
    assert result.hard_failed is False
    assert result.tolerance.protein_ok is False


def test_unknown_food_key_is_hard_fail():
    plan = _plan(("lunch", [("frittata_di_unicorno", 150)]))
    result = validate(plan, 2000.0, MacroTargets(120, 220, 60, 30, 2000), DB)
    assert result.hard_failed
    assert any("UNKNOWN_FOOD_KEY" in r for r in result.hard_fail_reasons)
    assert result.ok is False
    assert result.totals is None  # never summed once structurally invalid


def test_banned_tag_is_hard_fail_never_a_tolerance_question():
    plan = _plan(("lunch", [("salmone_cotto", 150), ("riso_bianco_cotto", 150)]))
    target_kcal, macros = target_macros_from_plan(plan)
    result = validate(plan, target_kcal, macros, DB, excluded_tags=("fish",))
    assert result.hard_failed
    assert any("BANNED_TAG_PRESENT:salmone_cotto" in r for r in result.hard_fail_reasons)


def test_grams_out_of_range_is_hard_fail():
    plan = _plan(("lunch", [("riso_bianco_cotto", 5000)]))
    result = validate(plan, 2000.0, MacroTargets(120, 220, 60, 30, 2000), DB)
    assert result.hard_failed
    assert any("GRAMS_OUT_OF_RANGE" in r for r in result.hard_fail_reasons)


def test_meal_grams_exceeded_is_hard_fail():
    plan = _plan(
        ("lunch", [("riso_bianco_cotto", 1000), ("petto_di_pollo_cotto", 1000), ("broccoli_cotti", 100)])
    )
    result = validate(plan, 2000.0, MacroTargets(120, 220, 60, 30, 2000), DB)
    assert result.hard_failed
    assert any("MEAL_GRAMS_EXCEEDED" in r for r in result.hard_fail_reasons)


def test_empty_plan_is_hard_fail():
    result = validate({"days": []}, 2000.0, MacroTargets(120, 220, 60, 30, 2000), DB)
    assert result.hard_failed
    assert "EMPTY_PLAN" in result.hard_fail_reasons


def test_multiple_hard_fails_all_reported():
    plan = _plan(("lunch", [("frittata_di_unicorno", 150), ("salmone_cotto", 150)]))
    result = validate(plan, 2000.0, MacroTargets(120, 220, 60, 30, 2000), DB, excluded_tags=("fish",))
    reasons = " ".join(result.hard_fail_reasons)
    assert "UNKNOWN_FOOD_KEY" in reasons
    assert "BANNED_TAG_PRESENT" in reasons


def test_items_returned_even_on_hard_fail_for_debugging():
    plan = _plan(("lunch", [("riso_bianco_cotto", 5000)]))
    result = validate(plan, 2000.0, MacroTargets(120, 220, 60, 30, 2000), DB)
    assert len(result.items) == 1
    assert result.items[0].food_key == "riso_bianco_cotto"
