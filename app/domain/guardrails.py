"""Safety guardrails, evaluated against a Profile before the engine computes
anything. Every row here is one parametrized test case in
tests/domain/test_guardrails.py, named after its ViolationCode.

The keyword screen in CONDITION_SCREEN is a best-effort fallback, not a
guarantee — it will miss conditions not phrased with a listed keyword. The
disclaimer is never delegated to this screen; it is attached unconditionally
by the API layer regardless of what guardrails find.
"""

from __future__ import annotations

from app.domain import references as ref
from app.domain.anthropometry import bmi, bmi_category
from app.domain.enums import BmiCategory, Goal, Severity, ViolationCode
from app.domain.models import Profile, Violation


def validate_profile(profile: Profile) -> list[Violation]:
    violations: list[Violation] = []

    # --- Age ---
    if profile.age_years < ref.AGE_CHILD_MAX:
        violations.append(
            Violation(ViolationCode.AGE_CHILD, Severity.REFUSE, "guardrail.age_child")
        )
    elif profile.age_years < ref.AGE_MINOR_MAX:
        violations.append(
            Violation(ViolationCode.AGE_MINOR, Severity.REFUSE, "guardrail.age_minor")
        )
    elif profile.age_years > ref.AGE_IMPLAUSIBLE_MIN:
        violations.append(
            Violation(ViolationCode.AGE_IMPLAUSIBLE, Severity.REFUSE, "guardrail.age_implausible")
        )
    elif profile.age_years >= ref.AGE_ELDERLY_MIN:
        violations.append(
            Violation(ViolationCode.AGE_ELDERLY, Severity.WARN, "guardrail.age_elderly")
        )

    # --- Height / weight plausibility ---
    if not (ref.HEIGHT_CM_MIN <= profile.height_cm <= ref.HEIGHT_CM_MAX):
        violations.append(
            Violation(
                ViolationCode.HEIGHT_RANGE,
                Severity.REFUSE,
                "guardrail.height_range",
                {"min": ref.HEIGHT_CM_MIN, "max": ref.HEIGHT_CM_MAX},
            )
        )
    if not (ref.WEIGHT_KG_MIN <= profile.weight_kg <= ref.WEIGHT_KG_MAX):
        violations.append(
            Violation(
                ViolationCode.WEIGHT_RANGE,
                Severity.REFUSE,
                "guardrail.weight_range",
                {"min": ref.WEIGHT_KG_MIN, "max": ref.WEIGHT_KG_MAX},
            )
        )

    # BMI-dependent checks only make sense with plausible height/weight.
    height_ok = ref.HEIGHT_CM_MIN <= profile.height_cm <= ref.HEIGHT_CM_MAX
    weight_ok = ref.WEIGHT_KG_MIN <= profile.weight_kg <= ref.WEIGHT_KG_MAX
    if height_ok and weight_ok:
        bmi_value = bmi(profile.weight_kg, profile.height_cm)
        category = bmi_category(bmi_value)

        if category == BmiCategory.SEVERE_UNDERWEIGHT:
            violations.append(
                Violation(
                    ViolationCode.BMI_SEVERE_UNDERWEIGHT,
                    Severity.REFUSE,
                    "guardrail.bmi_severe_underweight",
                    {"bmi": round(bmi_value, 1)},
                )
            )
        elif category == BmiCategory.UNDERWEIGHT:
            violations.append(
                Violation(
                    ViolationCode.BMI_UNDERWEIGHT,
                    Severity.WARN,
                    "guardrail.bmi_underweight",
                    {"bmi": round(bmi_value, 1)},
                )
            )
        elif category == BmiCategory.OBESE_III:
            violations.append(
                Violation(
                    ViolationCode.BMI_CLASS_III,
                    Severity.WARN,
                    "guardrail.bmi_class_iii",
                    {"bmi": round(bmi_value, 1)},
                )
            )

        if profile.goal == Goal.LOSE_WEIGHT and bmi_value < ref.BMI_UNDERWEIGHT_DEFICIT_BLOCK_MAX:
            violations.append(
                Violation(
                    ViolationCode.GOAL_CONFLICT_DEFICIT,
                    Severity.WARN,
                    "guardrail.goal_conflict_deficit",
                    {"bmi": round(bmi_value, 1)},
                )
            )

    # --- Condition screen (free-text health_notes) ---
    notes = profile.health_notes.lower()
    if any(keyword in notes for keyword in ref.CONDITION_SCREEN_KEYWORDS):
        violations.append(
            Violation(ViolationCode.CONDITION_SCREEN, Severity.REFUSE, "guardrail.condition_screen")
        )

    return violations


def has_refusal(violations: list[Violation]) -> bool:
    return any(v.severity == Severity.REFUSE for v in violations)


def effective_goal(profile: Profile, violations: list[Violation]) -> Goal:
    """GOAL_CONFLICT_DEFICIT overrides lose_weight to maintain — a deficit
    is not offered to someone already below a healthy BMI, regardless of
    what they asked for.
    """
    if any(v.code == ViolationCode.GOAL_CONFLICT_DEFICIT for v in violations):
        return Goal.MAINTAIN
    return profile.goal
