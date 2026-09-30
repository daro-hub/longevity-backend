"""BMI and body-weight reference calculations. See references.py for the
citation behind every constant used here.
"""

from __future__ import annotations

from app.domain import references as ref
from app.domain.enums import BmiCategory, Sex


def bmi(weight_kg: float, height_cm: float) -> float:
    height_m = height_cm / 100.0
    return weight_kg / (height_m * height_m)


def bmi_category(bmi_value: float) -> BmiCategory:
    if bmi_value < ref.BMI_SEVERE_UNDERWEIGHT_MAX:
        return BmiCategory.SEVERE_UNDERWEIGHT
    if bmi_value < ref.BMI_UNDERWEIGHT_MAX:
        return BmiCategory.UNDERWEIGHT
    if bmi_value < ref.BMI_NORMAL_MAX:
        return BmiCategory.NORMAL
    if bmi_value < ref.BMI_OVERWEIGHT_MAX:
        return BmiCategory.OVERWEIGHT
    if bmi_value < ref.BMI_OBESE_I_MAX:
        return BmiCategory.OBESE_I
    if bmi_value < ref.BMI_OBESE_II_MAX:
        return BmiCategory.OBESE_II
    return BmiCategory.OBESE_III


def ideal_body_weight_kg(height_cm: float, sex: Sex) -> float:
    """Devine formula. Height below the 5ft (152.4cm) base returns the base
    weight for that sex rather than going negative.
    """
    inches_over_base = max(0.0, (height_cm - ref.IBW_HEIGHT_THRESHOLD_CM) / ref.CM_PER_INCH)
    base = ref.IBW_BASE_KG_MALE if sex == Sex.MALE else ref.IBW_BASE_KG_FEMALE
    return base + ref.IBW_PER_INCH_OVER_KG * inches_over_base


def adjusted_body_weight_kg(weight_kg: float, height_cm: float, sex: Sex) -> float:
    """ABW = IBW + 0.25 * (actual - IBW). Used as the reference weight for
    protein dosing when BMI >= 30, so protein grams don't explode for
    high-BMI users and become unreachable inside the calorie target.
    """
    ibw = ideal_body_weight_kg(height_cm, sex)
    return ibw + ref.ADJUSTED_BW_FACTOR * (weight_kg - ibw)
