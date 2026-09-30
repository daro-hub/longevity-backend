import pytest

from app.domain.enums import ActivityLevel, Goal, Severity, Sex, ViolationCode
from app.domain.guardrails import effective_goal, has_refusal, validate_profile
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


@pytest.mark.parametrize(
    "overrides,expected_code,expected_severity",
    [
        ({"age_years": 10}, ViolationCode.AGE_CHILD, Severity.REFUSE),
        ({"age_years": 15}, ViolationCode.AGE_MINOR, Severity.REFUSE),
        ({"age_years": 101}, ViolationCode.AGE_IMPLAUSIBLE, Severity.REFUSE),
        ({"age_years": 92}, ViolationCode.AGE_ELDERLY, Severity.WARN),
        ({"height_cm": 50.0}, ViolationCode.HEIGHT_RANGE, Severity.REFUSE),
        ({"height_cm": 300.0}, ViolationCode.HEIGHT_RANGE, Severity.REFUSE),
        ({"weight_kg": 10.0}, ViolationCode.WEIGHT_RANGE, Severity.REFUSE),
        ({"weight_kg": 400.0}, ViolationCode.WEIGHT_RANGE, Severity.REFUSE),
        # BMI 16.0 at 175cm -> weight ~49kg
        ({"weight_kg": 49.0}, ViolationCode.BMI_SEVERE_UNDERWEIGHT, Severity.REFUSE),
        # BMI ~17.8 at 175cm -> weight ~54.5kg
        ({"weight_kg": 54.5}, ViolationCode.BMI_UNDERWEIGHT, Severity.WARN),
        # BMI ~41 at 175cm -> weight ~125kg
        ({"weight_kg": 125.0}, ViolationCode.BMI_CLASS_III, Severity.WARN),
        (
            {"weight_kg": 54.5, "goal": Goal.LOSE_WEIGHT},
            ViolationCode.GOAL_CONFLICT_DEFICIT,
            Severity.WARN,
        ),
        (
            {"health_notes": "Sono incinta di 6 mesi"},
            ViolationCode.CONDITION_SCREEN,
            Severity.REFUSE,
        ),
        (
            {"health_notes": "I have type 2 diabetes"},
            ViolationCode.CONDITION_SCREEN,
            Severity.REFUSE,
        ),
    ],
    ids=lambda v: str(v) if not isinstance(v, dict) else None,
)
def test_guardrail_branch(overrides, expected_code, expected_severity):
    profile = make_profile(**overrides)
    violations = validate_profile(profile)
    matching = [v for v in violations if v.code == expected_code]
    assert matching, f"expected {expected_code} in {[v.code for v in violations]}"
    assert matching[0].severity == expected_severity


def test_normal_profile_has_no_violations():
    profile = make_profile()
    violations = validate_profile(profile)
    assert violations == []
    assert has_refusal(violations) is False


def test_has_refusal_true_when_any_refuse_present():
    profile = make_profile(age_years=10)
    violations = validate_profile(profile)
    assert has_refusal(violations) is True


def test_has_refusal_false_for_warn_only():
    profile = make_profile(weight_kg=125.0)  # BMI_CLASS_III, warn only
    violations = validate_profile(profile)
    assert has_refusal(violations) is False


def test_effective_goal_overridden_on_conflict():
    profile = make_profile(weight_kg=54.5, goal=Goal.LOSE_WEIGHT)
    violations = validate_profile(profile)
    assert effective_goal(profile, violations) == Goal.MAINTAIN


def test_effective_goal_unchanged_without_conflict():
    profile = make_profile(goal=Goal.LOSE_WEIGHT)
    violations = validate_profile(profile)
    assert effective_goal(profile, violations) == Goal.LOSE_WEIGHT


def test_condition_screen_case_insensitive():
    profile = make_profile(health_notes="STO ALLATTAMENTO")
    violations = validate_profile(profile)
    assert any(v.code == ViolationCode.CONDITION_SCREEN for v in violations)
