"""Energy expenditure and calorie target calculations.

Note on the search for a feasible calorie target: this module deliberately
does NOT decide whether a given adjustment_pct is feasible against the
protein/fat floors — that would create a circular dependency with macros.py
(which needs a kcal figure to compute macro grams). The infeasibility search
(DEFICIT_RELAXED_FOR_FLOORS) lives in engine.py, which calls both this module
and macros.py and can see both sides.
"""

from __future__ import annotations

from app.domain import references as ref
from app.domain.enums import ActivityLevel, Sex
from app.domain.models import CalorieTarget
from app.domain.units import round_kcal


def bmr_mifflin_st_jeor(weight_kg: float, height_cm: float, age_years: int, sex: Sex) -> float:
    sex_const = ref.MSJ_SEX_CONST_MALE if sex == Sex.MALE else ref.MSJ_SEX_CONST_FEMALE
    return (
        ref.MSJ_WEIGHT_COEF * weight_kg
        + ref.MSJ_HEIGHT_COEF * height_cm
        - ref.MSJ_AGE_COEF * age_years
        + sex_const
    )


def tdee(bmr_kcal: float, activity: ActivityLevel) -> float:
    return bmr_kcal * ref.ACTIVITY_MULTIPLIERS[activity]


def calorie_target_for_adjustment(
    tdee_kcal: float,
    bmr_kcal: float,
    sex: Sex,
    adjustment_pct: float,
    rationale_code: str | None = None,
) -> CalorieTarget:
    """Apply a +/- adjustment to TDEE, then clamp to the higher of the two
    safety floors: 1.1x BMR, or the sex-specific absolute floor.
    """
    raw = tdee_kcal * (1.0 + adjustment_pct)
    bmr_floor = ref.BMR_RELATIVE_FLOOR_FACTOR * bmr_kcal
    abs_floor = ref.ABSOLUTE_CALORIE_FLOOR[sex]
    floor = max(bmr_floor, abs_floor)

    floor_applied = raw < floor
    kcal = max(raw, floor)

    return CalorieTarget(
        kcal=round_kcal(kcal),
        tdee_kcal=tdee_kcal,
        bmr_kcal=bmr_kcal,
        applied_adjustment_pct=adjustment_pct,
        floor_applied=floor_applied,
        rationale_code=rationale_code,
    )
