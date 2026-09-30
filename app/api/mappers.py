"""Conversions between the API's pydantic schemas and the domain engine's
plain dataclasses. Kept separate from both so neither layer needs to know
about the other's shape.
"""

from __future__ import annotations

from app.api.schemas import (
    CalorieTargetOut,
    MacroTargetsOut,
    ProfileIn,
    TargetsOut,
    TargetsResponse,
    ViolationOut,
)
from app.domain import references as ref
from app.domain.messages import DISCLAIMER, guardrail_message
from app.domain.models import Profile, TargetsResult, Violation


def profile_in_to_domain(profile_in: ProfileIn) -> Profile:
    return Profile(
        age_years=profile_in.age_years,
        sex=profile_in.sex,
        height_cm=profile_in.height_cm,
        weight_kg=profile_in.weight_kg,
        activity_level=profile_in.activity_level,
        goal=profile_in.goal,
        health_notes=profile_in.health_notes,
    )


def _violation_to_out(violation: Violation, locale: str) -> ViolationOut:
    return ViolationOut(
        code=violation.code.value,
        severity=violation.severity.value,
        message=guardrail_message(violation.message_key, locale),
    )


def targets_result_to_response(result: TargetsResult, locale: str) -> TargetsResponse:
    violations_out = [_violation_to_out(v, locale) for v in result.violations]
    disclaimer = DISCLAIMER.get(locale, DISCLAIMER["it"])

    if result.refused or result.targets is None:
        return TargetsResponse(
            refused=True,
            targets=None,
            violations=violations_out,
            disclaimer=disclaimer,
        )

    t = result.targets
    targets_out = TargetsOut(
        bmi=t.bmi,
        bmi_category=t.bmi_category,
        calories=CalorieTargetOut(
            kcal=t.calories.kcal,
            tdee_kcal=t.calories.tdee_kcal,
            bmr_kcal=t.calories.bmr_kcal,
            applied_adjustment_pct=t.calories.applied_adjustment_pct,
            floor_applied=t.calories.floor_applied,
            uncertainty_pct=ref.TDEE_UNCERTAINTY_PCT,
        ),
        macros=MacroTargetsOut(
            protein_g=t.macros.protein_g,
            carb_g=t.macros.carb_g,
            fat_g=t.macros.fat_g,
            fiber_g=t.macros.fiber_g,
            kcal_from_macros=t.macros.kcal_from_macros,
        ),
        hydration_ml=t.hydration_ml,
        engine_version=t.engine_version,
        warnings=[_violation_to_out(w, locale) for w in t.warnings],
    )

    return TargetsResponse(
        refused=False,
        targets=targets_out,
        violations=violations_out,
        disclaimer=disclaimer,
    )
