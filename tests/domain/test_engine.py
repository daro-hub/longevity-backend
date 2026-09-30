import pytest

from app.domain.engine import compute_targets
from app.domain.enums import ActivityLevel, BmiCategory, Goal, Sex, ViolationCode
from app.domain.models import Profile


def make_profile(**overrides) -> Profile:
    defaults = dict(
        age_years=30,
        sex=Sex.MALE,
        height_cm=175.0,
        weight_kg=75.0,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.MAINTAIN,
        health_notes="",
    )
    defaults.update(overrides)
    return Profile(**defaults)


def test_normal_profile_produces_targets():
    result = compute_targets(make_profile())
    assert result.refused is False
    assert result.targets is not None
    assert result.targets.bmi > 0
    assert result.targets.calories.kcal > 0
    assert result.targets.macros.protein_g > 0


def test_refused_profile_has_no_targets():
    result = compute_targets(make_profile(age_years=10))
    assert result.refused is True
    assert result.targets is None
    assert any(v.code == ViolationCode.AGE_CHILD for v in result.violations)


def test_atwater_identity_holds_on_final_targets():
    result = compute_targets(make_profile(goal=Goal.LOSE_WEIGHT))
    m = result.targets.macros
    recomputed = 4 * m.protein_g + 4 * m.carb_g + 9 * m.fat_g
    assert recomputed == pytest.approx(m.kcal_from_macros, abs=0.01)
    # The calorie target exposed to callers must match the macro-derived kcal.
    assert result.targets.calories.kcal == pytest.approx(m.kcal_from_macros, abs=0.01)


def test_engine_version_is_stamped():
    result = compute_targets(make_profile())
    assert result.targets.engine_version


def test_final_targets_are_always_feasible_across_a_wide_scan():
    # With the current reference constants, protein/fat floors are
    # generous enough relative to TDEE that infeasibility is rare in
    # practice for realistic adult bodies -- but the invariant must hold
    # everywhere it's reachable, not just in a hand-picked example.
    for weight in range(50, 180, 15):
        for height in range(150, 195, 15):
            profile = make_profile(
                height_cm=float(height),
                weight_kg=float(weight),
                activity_level=ActivityLevel.SEDENTARY,
                goal=Goal.LOSE_WEIGHT,
            )
            result = compute_targets(profile)
            if result.refused:
                continue
            m = result.targets.macros
            consumed = m.protein_g * 4 + m.fat_g * 9
            assert consumed <= result.targets.calories.kcal + 1, (weight, height)
            assert m.carb_g >= 0, (weight, height)


def test_deficit_relaxation_mechanism_engages_when_floors_dont_fit(monkeypatch):
    # The realistic scan above shows infeasibility essentially never
    # happens with today's constants -- which is exactly why this
    # mechanism needs its own direct test rather than relying on finding
    # a naturally-occurring example. Force the first candidate to be
    # infeasible and confirm the engine relaxes to the next one instead
    # of returning negative carbs or silently keeping the aggressive
    # deficit.
    from app.domain import macros as macros_module

    real_is_feasible = macros_module.is_feasible
    calls = {"n": 0}

    def flaky_is_feasible(kcal, protein_g, fat_g):
        calls["n"] += 1
        if calls["n"] == 1:
            return False  # force the base -20% deficit to be rejected
        return real_is_feasible(kcal, protein_g, fat_g)

    monkeypatch.setattr(macros_module, "is_feasible", flaky_is_feasible)

    profile = make_profile(goal=Goal.LOSE_WEIGHT)
    result = compute_targets(profile)

    assert result.refused is False
    assert any(v.code == ViolationCode.DEFICIT_RELAXED_FOR_FLOORS for v in result.violations)
    # Relaxed adjustment must be less aggressive (closer to zero) than -20%.
    assert result.targets.calories.applied_adjustment_pct > -0.20


def test_bmi_class_iii_caps_deficit_at_15_percent():
    profile = make_profile(weight_kg=125.0, goal=Goal.LOSE_WEIGHT)  # BMI ~41
    result = compute_targets(profile)
    assert result.targets.bmi_category == BmiCategory.OBESE_III
    assert result.targets.calories.applied_adjustment_pct >= -0.15 - 1e-9


def test_underweight_goal_conflict_forces_maintain_zero_adjustment():
    profile = make_profile(weight_kg=54.5, goal=Goal.LOSE_WEIGHT)  # BMI ~17.8
    result = compute_targets(profile)
    assert result.targets.calories.applied_adjustment_pct == pytest.approx(0.0)


def test_severe_underweight_refuses_plan():
    profile = make_profile(weight_kg=49.0)  # BMI ~16
    result = compute_targets(profile)
    assert result.refused is True


def test_minor_refuses_targets():
    profile = make_profile(age_years=15)
    result = compute_targets(profile)
    assert result.refused is True


def test_condition_screen_refuses_targets():
    profile = make_profile(health_notes="sono in dialisi da un anno")
    result = compute_targets(profile)
    assert result.refused is True
    assert any(v.code == ViolationCode.CONDITION_SCREEN for v in result.violations)


def test_relaxation_exhausted_still_returns_best_effort_targets(monkeypatch):
    # If even a zero-adjustment (maintenance) target can't fit the floors,
    # the engine must still return its best-effort last attempt rather than
    # raising or returning nothing -- macro_targets' own carb-clamp is the
    # true last line of defense at that point.
    from app.domain import macros as macros_module

    monkeypatch.setattr(macros_module, "is_feasible", lambda kcal, protein_g, fat_g: False)

    profile = make_profile(goal=Goal.LOSE_WEIGHT)
    result = compute_targets(profile)

    assert result.refused is False
    assert result.targets is not None
    assert any(v.code == ViolationCode.DEFICIT_RELAXED_FOR_FLOORS for v in result.violations)
    assert result.targets.calories.applied_adjustment_pct == pytest.approx(0.0)


def test_elderly_warning_still_produces_targets():
    profile = make_profile(age_years=92)
    result = compute_targets(profile)
    assert result.refused is False
    assert any(v.code == ViolationCode.AGE_ELDERLY for v in result.violations)
