"""The single public entrypoint of the deterministic domain engine.

compute_targets(profile) orchestrates guardrails, energy, and macros into
one result. This is the only function the API layer (or a script, or a
test) should call to get real numbers for a user profile — everything else
in this package is a building block for this function.
"""

from __future__ import annotations

from dataclasses import replace

from app.domain import energy, guardrails, macros
from app.domain import references as ref
from app.domain.anthropometry import bmi, bmi_category
from app.domain.enums import Severity, ViolationCode
from app.domain.models import Profile, Targets, TargetsResult, Violation

ENGINE_VERSION = "1.0.0"


def compute_targets(profile: Profile) -> TargetsResult:
    violations = guardrails.validate_profile(profile)

    if guardrails.has_refusal(violations):
        return TargetsResult(targets=None, violations=tuple(violations))

    goal = guardrails.effective_goal(profile, violations)

    bmi_value = bmi(profile.weight_kg, profile.height_cm)
    category = bmi_category(bmi_value)

    bmr = energy.bmr_mifflin_st_jeor(
        profile.weight_kg, profile.height_cm, profile.age_years, profile.sex
    )
    tdee_kcal = energy.tdee(bmr, profile.activity_level)

    base_adjustment = ref.GOAL_TDEE_ADJUSTMENT[goal]
    if category == category.OBESE_III and base_adjustment < 0:
        base_adjustment = max(base_adjustment, -ref.BMI_CLASS_III_MAX_DEFICIT_PCT)

    calorie_target, macro_result, relaxed = _find_feasible_targets(
        tdee_kcal, bmr, profile, goal, bmi_value, base_adjustment
    )

    extra_violations: list[Violation] = []
    if relaxed:
        extra_violations.append(
            Violation(
                ViolationCode.DEFICIT_RELAXED_FOR_FLOORS,
                Severity.WARN,
                "guardrail.deficit_relaxed_for_floors",
            )
        )

    all_violations = tuple(violations) + tuple(extra_violations)
    warnings = tuple(v for v in all_violations if v.severity == Severity.WARN)

    hydration = macros.hydration_target_ml(profile.weight_kg, profile.activity_level)

    targets = Targets(
        bmi=round(bmi_value, 1),
        bmi_category=category,
        calories=calorie_target,
        macros=macro_result,
        hydration_ml=hydration,
        engine_version=ENGINE_VERSION,
        warnings=warnings,
    )

    return TargetsResult(targets=targets, violations=all_violations)


def _find_feasible_targets(tdee_kcal, bmr, profile, goal, bmi_value, base_adjustment):
    """Try base_adjustment first; if it's a deficit and the protein/fat
    floors don't fit inside the resulting calorie target, relax the deficit
    (never the floors) through DEFICIT_RELAXATION_STEPS until it fits.
    """
    candidates = [base_adjustment]
    if base_adjustment < 0:
        for step in ref.DEFICIT_RELAXATION_STEPS:
            magnitude = -step
            if magnitude > base_adjustment:  # less aggressive than what we already tried
                candidates.append(magnitude)

    last_calorie_target = None
    last_macro_result = None

    for i, adjustment_pct in enumerate(candidates):
        rationale = ViolationCode.DEFICIT_RELAXED_FOR_FLOORS.value if i > 0 else None
        calorie_target = energy.calorie_target_for_adjustment(
            tdee_kcal, bmr, profile.sex, adjustment_pct, rationale_code=rationale
        )
        protein_g = macros.protein_target_g(
            profile.weight_kg, profile.height_cm, profile.sex, profile.age_years, goal, bmi_value
        )
        fat_g = macros.fat_floor_g(calorie_target.kcal, profile.weight_kg)

        last_calorie_target = calorie_target
        last_macro_result = macros.macro_targets(
            calorie_target.kcal,
            profile.weight_kg,
            profile.height_cm,
            profile.sex,
            profile.age_years,
            goal,
            bmi_value,
        )

        if macros.is_feasible(calorie_target.kcal, protein_g, fat_g):
            final_calorie_target = replace(calorie_target, kcal=last_macro_result.kcal_from_macros)
            return final_calorie_target, last_macro_result, (i > 0)

    # Nothing was feasible even at zero adjustment — use the last attempt;
    # macro_targets already clamps carbs to zero defensively in this case.
    final_calorie_target = replace(last_calorie_target, kcal=last_macro_result.kcal_from_macros)
    return final_calorie_target, last_macro_result, len(candidates) > 1
