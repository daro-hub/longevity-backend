import pytest

from app.domain.food_db import load_food_db
from app.domain.models import MacroTargets
from app.domain.nutrition import PlanItem, total_macros
from app.domain.plan_fitting import fit_to_targets
from app.domain.plan_tolerance import check_tolerance

DB = load_food_db()


def make_macros(kcal, protein, carb, fat, fiber):
    return MacroTargets(protein_g=protein, carb_g=carb, fat_g=fat, fiber_g=fiber, kcal_from_macros=kcal)


def test_empty_items_fails_cleanly():
    result = fit_to_targets([], 2000.0, make_macros(2000, 120, 220, 60, 30), DB)
    assert result.success is False
    assert result.items == []


def test_already_within_tolerance_returns_unchanged():
    # Construct items whose totals are already close to target.
    items = [
        PlanItem(food_key="riso_bianco_cotto", grams=300),
        PlanItem(food_key="petto_di_pollo_cotto", grams=250),
        PlanItem(food_key="olio_oliva", grams=20),
    ]
    totals = total_macros(items, DB)
    macros = make_macros(totals.kcal, totals.protein_g, totals.carb_g, totals.fat_g, totals.fiber_g)
    result = fit_to_targets(items, totals.kcal, macros, DB)
    assert result.success
    assert result.iterations == 1


def test_proportional_scaling_fixes_uniform_undersize():
    # A plan that's exactly half the target, scaled uniformly -> scaling
    # alone (pass 1) should fix it since ratios stay identical.
    items = [
        PlanItem(food_key="riso_bianco_cotto", grams=100),
        PlanItem(food_key="petto_di_pollo_cotto", grams=100),
    ]
    totals = total_macros(items, DB)
    # Target is double the current totals -> scale factor 2, but clamped to
    # FIT_SCALE_MAX (1.25), so it won't reach it in one pass. Use a target
    # within the clamp range instead.
    target_kcal = totals.kcal * 1.2
    macros = make_macros(
        target_kcal,
        totals.protein_g * 1.2,
        totals.carb_g * 1.2,
        totals.fat_g * 1.2,
        totals.fiber_g * 1.2,
    )
    result = fit_to_targets(items, target_kcal, macros, DB)
    assert result.success


def test_scale_is_clamped_not_unbounded():
    # Wildly undersized plan: pass-1 scaling alone is clamped to 1.25x per
    # call, so a single fit_to_targets call can't 10x it. The greedy pass
    # can still nudge the (only) item further across iterations -- that's
    # a real limitation (it can't invent a new food), but grams must stay
    # within the absolute domain bound regardless.
    items = [PlanItem(food_key="insalata_verde", grams=50)]
    totals = total_macros(items, DB)
    target_kcal = totals.kcal * 10
    macros = make_macros(target_kcal, 150, 300, 80, 30)
    result = fit_to_targets(items, target_kcal, macros, DB)
    # This target is genuinely unreachable with lettuce alone.
    assert result.success is False
    assert result.items[0].grams <= 1000.0


def test_greedy_pass_raises_protein_when_short():
    # Rice-only plan is protein-light; add a high-protein item and expect
    # the greedy pass to lean on whichever item has the highest protein
    # density when protein is short.
    items = [
        PlanItem(food_key="riso_bianco_cotto", grams=300),
        PlanItem(food_key="petto_di_pollo_cotto", grams=50),
    ]
    totals = total_macros(items, DB)
    # Ask for more protein than currently present, kcal roughly matched.
    macros = make_macros(totals.kcal, totals.protein_g + 15, totals.carb_g, totals.fat_g, 5)
    result = fit_to_targets(items, totals.kcal, macros, DB)
    chicken_before = 50
    chicken_after = next(i.grams for i in result.items if i.food_key == "petto_di_pollo_cotto")
    assert chicken_after > chicken_before


def test_result_items_grams_stay_within_bounds():
    items = [PlanItem(food_key="olio_oliva", grams=5)]
    macros = make_macros(5000, 10, 10, 500, 5)
    result = fit_to_targets(items, 5000.0, macros, DB)
    for item in result.items:
        assert 1.0 <= item.grams <= 1000.0


def test_unreachable_target_reports_failure_not_exception():
    # A single lettuce leaf can never hit a 3000kcal/200g-protein target;
    # must report success=False rather than raising or looping forever.
    items = [PlanItem(food_key="insalata_verde", grams=30)]
    macros = make_macros(3000, 200, 300, 100, 30)
    result = fit_to_targets(items, 3000.0, macros, DB)
    assert result.success is False
    assert result.iterations == 10  # exhausted FIT_MAX_GREEDY_ITERATIONS


def test_greedy_pass_lowers_fat_when_over():
    items = [
        PlanItem(food_key="petto_di_pollo_cotto", grams=200),
        PlanItem(food_key="olio_oliva", grams=40),
    ]
    totals = total_macros(items, DB)
    macros = make_macros(totals.kcal, totals.protein_g, totals.carb_g, totals.fat_g - 15, 5)
    result = fit_to_targets(items, totals.kcal, macros, DB)
    oil_before = 40
    oil_after = next(i.grams for i in result.items if i.food_key == "olio_oliva")
    assert oil_after < oil_before


def test_converges_mid_greedy_loop_not_just_first_or_last_iteration():
    # A small protein shortfall should be nudged closed within a couple of
    # greedy iterations -- neither instantly (pass 1 alone) nor only after
    # exhausting every iteration.
    items = [
        PlanItem(food_key="riso_bianco_cotto", grams=250),
        PlanItem(food_key="petto_di_pollo_cotto", grams=150),
        PlanItem(food_key="olio_oliva", grams=10),
    ]
    totals = total_macros(items, DB)
    macros = make_macros(totals.kcal, totals.protein_g + 3, totals.carb_g, totals.fat_g, totals.fiber_g)
    result = fit_to_targets(items, totals.kcal, macros, DB)
    assert result.success
    assert 1 < result.iterations < 10


def test_highest_density_index_skips_items_with_unknown_food_key():
    # Defensive branch: fit_to_targets is only ever called on items the
    # validator already confirmed exist in food_db, but this helper
    # doesn't assume that -- an unknown key must be skipped, not crash.
    from app.domain.plan_fitting import _highest_density_index

    items = [
        PlanItem(food_key="does_not_exist", grams=100),
        PlanItem(food_key="petto_di_pollo_cotto", grams=100),
    ]
    idx = _highest_density_index(items, DB, "protein_g")
    assert idx == 1


def test_final_state_matches_check_tolerance_when_successful():
    items = [
        PlanItem(food_key="riso_bianco_cotto", grams=250),
        PlanItem(food_key="petto_di_pollo_cotto", grams=200),
        PlanItem(food_key="olio_oliva", grams=15),
        PlanItem(food_key="broccoli_cotti", grams=150),
    ]
    totals = total_macros(items, DB)
    macros = make_macros(totals.kcal, totals.protein_g, totals.carb_g, totals.fat_g, totals.fiber_g * 0.9)
    result = fit_to_targets(items, totals.kcal, macros, DB)
    final_totals = total_macros(result.items, DB)
    check = check_tolerance(final_totals, totals.kcal, macros)
    assert check.all_ok == result.success
