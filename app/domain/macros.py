"""Macro-nutrient targets.

Rounding order matters here (see units.py): protein and fat are computed
first in grams, carbs are the residual, and only after all three are rounded
to whole grams is kcal recomputed from those rounded grams
(4*P + 4*C + 9*F). That recomputed value — not the pre-rounding kcal target
— is the authoritative calorie figure the plan validator checks against.
Returning the pre-rounding figure would hand the validator a target that no
integer-gram plan could ever hit exactly.

Fiber is deliberately excluded from the kcal identity (see
references.ATWATER_FACTORS): it's tracked as a target but not assigned its
own ~2 kcal/g, so 4P+4C+9F == kcal holds exactly.
"""

from __future__ import annotations

from app.domain import references as ref
from app.domain.anthropometry import adjusted_body_weight_kg
from app.domain.enums import ActivityLevel, Goal, Sex
from app.domain.models import MacroTargets
from app.domain.units import clamp, round_grams, round_kcal, round_ml


def _reference_weight_kg(weight_kg: float, height_cm: float, sex: Sex, bmi_value: float) -> float:
    """Actual weight, unless BMI >= 30 (obese_I and above), in which case
    adjusted body weight — otherwise protein/fat grams computed per
    kilogram of actual weight explode for high-BMI users and become
    unreachable inside the calorie target.
    """
    if bmi_value >= ref.BMI_OVERWEIGHT_MAX:
        return adjusted_body_weight_kg(weight_kg, height_cm, sex)
    return weight_kg


def protein_target_g(
    weight_kg: float,
    height_cm: float,
    sex: Sex,
    age_years: int,
    goal: Goal,
    bmi_value: float,
) -> float:
    ref_weight = _reference_weight_kg(weight_kg, height_cm, sex, bmi_value)
    g_per_kg = ref.PROTEIN_G_PER_KG[goal]
    if age_years >= ref.PROTEIN_ELDERLY_AGE_THRESHOLD:
        g_per_kg = max(g_per_kg, ref.PROTEIN_G_PER_KG_ELDERLY_MIN)
    g_per_kg = min(g_per_kg, ref.PROTEIN_G_PER_KG_MAX)
    return ref_weight * g_per_kg


def fat_floor_g(kcal: float, weight_kg: float) -> float:
    by_weight = ref.FAT_G_PER_KG_MIN * weight_kg
    by_kcal_pct = (ref.FAT_KCAL_PCT_MIN * kcal) / ref.KCAL_PER_G_FAT
    return max(by_weight, by_kcal_pct)


def fat_ceiling_g(kcal: float) -> float:
    return (ref.FAT_KCAL_PCT_MAX * kcal) / ref.KCAL_PER_G_FAT


def is_feasible(kcal: float, protein_g: float, fat_g: float) -> bool:
    """Whether the protein + fat floors leave any room for carbs (>= 0)
    within the given calorie target.
    """
    consumed = protein_g * ref.KCAL_PER_G_PROTEIN + fat_g * ref.KCAL_PER_G_FAT
    return consumed <= kcal


def fiber_target_g(kcal: float) -> float:
    return max(ref.FIBER_G_PER_1000KCAL * (kcal / 1000.0), ref.FIBER_G_MIN)


def hydration_target_ml(weight_kg: float, activity: ActivityLevel) -> float:
    ml = ref.HYDRATION_ML_PER_KG * weight_kg
    if activity == ActivityLevel.VERY_ACTIVE:
        ml += ref.HYDRATION_ML_VERY_ACTIVE_BONUS
    return round_ml(clamp(ml, ref.HYDRATION_ML_MIN, ref.HYDRATION_ML_MAX))


def macro_targets(
    kcal: float,
    weight_kg: float,
    height_cm: float,
    sex: Sex,
    age_years: int,
    goal: Goal,
    bmi_value: float,
) -> MacroTargets:
    """Compute protein and fat first, carbs as the residual, round all
    three to whole grams, then recompute kcal from those rounded grams.

    Caller (engine.py) is responsible for ensuring feasibility via
    is_feasible() before calling this — carbs are clamped to zero here as a
    last-resort defensive measure, but that should never trigger once the
    engine's relaxation search has run.
    """
    protein_g_raw = protein_target_g(weight_kg, height_cm, sex, age_years, goal, bmi_value)
    fat_g_raw = max(fat_floor_g(kcal, weight_kg), 0.0)
    fat_g_raw = min(fat_g_raw, fat_ceiling_g(kcal)) if fat_ceiling_g(kcal) >= fat_floor_g(kcal, weight_kg) else fat_g_raw

    protein_kcal = protein_g_raw * ref.KCAL_PER_G_PROTEIN
    fat_kcal = fat_g_raw * ref.KCAL_PER_G_FAT
    carb_kcal_raw = max(0.0, kcal - protein_kcal - fat_kcal)
    carb_g_raw = carb_kcal_raw / ref.KCAL_PER_G_CARB

    protein_g = round_grams(protein_g_raw)
    fat_g = round_grams(fat_g_raw)
    carb_g = round_grams(carb_g_raw)

    kcal_from_macros = (
        protein_g * ref.KCAL_PER_G_PROTEIN
        + carb_g * ref.KCAL_PER_G_CARB
        + fat_g * ref.KCAL_PER_G_FAT
    )

    return MacroTargets(
        protein_g=protein_g,
        carb_g=carb_g,
        fat_g=fat_g,
        fiber_g=round_grams(fiber_target_g(kcal)),
        kcal_from_macros=round_kcal(kcal_from_macros),
    )
