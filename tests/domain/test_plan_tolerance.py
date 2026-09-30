import pytest

from app.domain.models import MacroTargets
from app.domain.nutrition import PlanTotals
from app.domain.plan_tolerance import check_tolerance

TARGET_KCAL = 2000.0
MACROS = MacroTargets(protein_g=120, carb_g=220, fat_g=60, fiber_g=30, kcal_from_macros=2000)


def test_exact_match_is_ok():
    totals = PlanTotals(kcal=2000, protein_g=120, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.all_ok


def test_kcal_within_band_ok():
    # 5% of 2000 = 100; 50 kcal over is within band
    totals = PlanTotals(kcal=2050, protein_g=120, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.kcal_ok


def test_kcal_outside_band_fails():
    totals = PlanTotals(kcal=2300, protein_g=120, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.kcal_ok is False
    assert not result.all_ok


def test_kcal_min_absolute_band_for_small_targets():
    # 5% of 400 = 20, but the absolute floor is 75kcal
    small_macros = MacroTargets(protein_g=30, carb_g=40, fat_g=10, fiber_g=10, kcal_from_macros=400)
    totals = PlanTotals(kcal=460, protein_g=30, carb_g=40, fat_g=10, fiber_g=10)
    result = check_tolerance(totals, 400.0, small_macros)
    assert result.kcal_ok  # 60kcal over, within the 75kcal absolute floor


def test_protein_undershoot_band_is_narrow():
    # -5% of 120 = -6; -10 is outside
    totals = PlanTotals(kcal=2000, protein_g=110, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.protein_ok is False


def test_protein_overshoot_band_is_generous():
    # +25% of 120 = +30 -> 150g is right at the edge, ok
    totals = PlanTotals(kcal=2000, protein_g=150, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.protein_ok


def test_protein_overshoot_beyond_band_fails():
    totals = PlanTotals(kcal=2000, protein_g=170, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.protein_ok is False


def test_fat_symmetric_band():
    # 15% of 60 = 9
    totals_over = PlanTotals(kcal=2000, protein_g=120, carb_g=220, fat_g=70, fiber_g=30)
    totals_under = PlanTotals(kcal=2000, protein_g=120, carb_g=220, fat_g=50, fiber_g=30)
    assert check_tolerance(totals_over, TARGET_KCAL, MACROS).fat_ok is False
    assert check_tolerance(totals_under, TARGET_KCAL, MACROS).fat_ok is False
    totals_ok = PlanTotals(kcal=2000, protein_g=120, carb_g=220, fat_g=65, fiber_g=30)
    assert check_tolerance(totals_ok, TARGET_KCAL, MACROS).fat_ok


def test_fiber_one_sided_no_ceiling():
    # way above target fiber should still be ok (no ceiling)
    totals = PlanTotals(kcal=2000, protein_g=120, carb_g=220, fat_g=60, fiber_g=80)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.fiber_ok


def test_fiber_below_90_percent_fails():
    totals = PlanTotals(kcal=2000, protein_g=120, carb_g=220, fat_g=60, fiber_g=20)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.fiber_ok is False


def test_deltas_are_signed():
    totals = PlanTotals(kcal=1900, protein_g=100, carb_g=220, fat_g=60, fiber_g=30)
    result = check_tolerance(totals, TARGET_KCAL, MACROS)
    assert result.kcal_delta == pytest.approx(-100.0)
    assert result.protein_delta == pytest.approx(-20.0)
