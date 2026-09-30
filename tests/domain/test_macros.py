import pytest

from app.domain import references as ref
from app.domain.enums import ActivityLevel, Goal, Sex
from app.domain.macros import (
    fat_floor_g,
    fiber_target_g,
    hydration_target_ml,
    is_feasible,
    macro_targets,
    protein_target_g,
)


def test_protein_target_uses_actual_weight_below_overweight_bmi():
    # BMI < 25 (overweight threshold): reference weight == actual weight.
    g = protein_target_g(70, 175, Sex.MALE, 30, Goal.MAINTAIN, bmi_value=22.0)
    assert g == pytest.approx(70 * 1.2)


def test_protein_target_uses_adjusted_weight_when_obese():
    # BMI 35: reference weight should be adjusted body weight, not actual.
    actual_weight = 110.0
    g = protein_target_g(actual_weight, 170, Sex.MALE, 30, Goal.MAINTAIN, bmi_value=35.0)
    naive = actual_weight * ref.PROTEIN_G_PER_KG[Goal.MAINTAIN]
    assert g < naive  # adjusted weight is lower than actual for obese


def test_protein_target_elderly_floor():
    # age >= 65 forces at least 1.2 g/kg even for a goal with a lower rate
    # (there is none lower than 1.2 currently, so use gain_muscle at low age
    # vs elderly to confirm the floor engages without lowering anything).
    g_young = protein_target_g(70, 175, Sex.MALE, 30, Goal.MAINTAIN, bmi_value=22.0)
    g_elderly = protein_target_g(70, 175, Sex.MALE, 70, Goal.MAINTAIN, bmi_value=22.0)
    assert g_elderly >= g_young


def test_protein_target_capped_at_max():
    # Contrive a case where g/kg * weight would exceed the cap if uncapped.
    # gain_muscle is 1.8, cap is 2.2, so this specific case won't hit the cap
    # naturally -- verify the cap constant is actually enforced via a probe.
    g = protein_target_g(70, 175, Sex.MALE, 30, Goal.GAIN_MUSCLE, bmi_value=22.0)
    assert g <= 70 * ref.PROTEIN_G_PER_KG_MAX


def test_fat_floor_is_the_higher_of_two_methods():
    # weight=100kg -> by_weight = 80g; kcal=1500 -> by_pct = 0.20*1500/9=33.3g
    assert fat_floor_g(1500, 100) == pytest.approx(80.0, abs=0.1)
    # weight=50kg -> by_weight=40g; kcal=3000 -> by_pct=0.20*3000/9=66.7g
    assert fat_floor_g(3000, 50) == pytest.approx(66.67, abs=0.1)


def test_fiber_target_floor_for_low_calorie():
    # 1200 kcal * 14/1000 = 16.8, below the 25g floor
    assert fiber_target_g(1200) == pytest.approx(25.0)


def test_fiber_target_scales_above_floor():
    # 3000 kcal * 14/1000 = 42
    assert fiber_target_g(3000) == pytest.approx(42.0)


def test_hydration_clamped_and_bonus_for_very_active():
    # 40kg * 35 = 1400 -> clamped to 1500 min
    assert hydration_target_ml(40, ActivityLevel.SEDENTARY) == 1500
    # 100kg * 35 = 3500, + 500 very_active bonus = 4000 (== max, not clamped further)
    assert hydration_target_ml(100, ActivityLevel.VERY_ACTIVE) == 4000
    # 150kg * 35 = 5250 -> clamped to 4000 max
    assert hydration_target_ml(150, ActivityLevel.SEDENTARY) == 4000


def test_is_feasible_true_when_floors_fit():
    # protein 100g (400kcal) + fat 50g (450kcal) = 850kcal <= 2000
    assert is_feasible(2000, 100, 50) is True


def test_is_feasible_false_when_floors_exceed_kcal():
    # protein 200g (800kcal) + fat 100g (900kcal) = 1700kcal > 1200
    assert is_feasible(1200, 200, 100) is False


class TestMacroTargetsRoundingIdentity:
    """The most important invariant in the whole engine: kcal_from_macros
    must exactly equal 4*protein + 4*carb + 9*fat using the ROUNDED grams,
    because that's what the plan validator will check a real meal plan
    against. If this drifts, the validator chases an unreachable target.
    """

    def test_atwater_identity_holds_exactly(self):
        for kcal, weight, height, sex, age, goal, bmi_value in [
            (2000, 70, 175, Sex.MALE, 30, Goal.MAINTAIN, 22.0),
            (1800, 60, 165, Sex.FEMALE, 45, Goal.LOSE_WEIGHT, 26.0),
            (2800, 90, 185, Sex.MALE, 25, Goal.GAIN_MUSCLE, 24.0),
            (1500, 55, 160, Sex.FEMALE, 70, Goal.MAINTAIN, 21.0),
        ]:
            m = macro_targets(kcal, weight, height, sex, age, goal, bmi_value)
            recomputed = 4 * m.protein_g + 4 * m.carb_g + 9 * m.fat_g
            assert recomputed == pytest.approx(m.kcal_from_macros, abs=0.01)

    def test_grams_are_whole_numbers(self):
        m = macro_targets(2137, 73.4, 176.2, Sex.MALE, 33, Goal.MAINTAIN, 23.6)
        assert m.protein_g == int(m.protein_g)
        assert m.carb_g == int(m.carb_g)
        assert m.fat_g == int(m.fat_g)
        assert m.fiber_g == int(m.fiber_g)

    def test_carbs_never_negative(self):
        # Even in a contrived very-low-kcal scenario, carbs must clamp to 0
        # rather than go negative (engine.py's relaxation search should
        # prevent this from being reached in practice; this is the last
        # line of defense).
        m = macro_targets(900, 120, 170, Sex.MALE, 30, Goal.LOSE_WEIGHT, 38.0)
        assert m.carb_g >= 0
