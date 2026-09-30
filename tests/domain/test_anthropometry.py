import pytest

from app.domain.anthropometry import (
    adjusted_body_weight_kg,
    bmi,
    bmi_category,
    ideal_body_weight_kg,
)
from app.domain.enums import BmiCategory, Sex


def test_bmi_basic():
    # 70kg, 175cm -> 70 / 1.75^2 = 22.857...
    assert bmi(70, 175) == pytest.approx(22.857, abs=0.01)


@pytest.mark.parametrize(
    "bmi_value,expected",
    [
        (16.9, BmiCategory.SEVERE_UNDERWEIGHT),
        (17.0, BmiCategory.UNDERWEIGHT),
        (18.4, BmiCategory.UNDERWEIGHT),
        (18.5, BmiCategory.NORMAL),
        (24.9, BmiCategory.NORMAL),
        (25.0, BmiCategory.OVERWEIGHT),
        (29.9, BmiCategory.OVERWEIGHT),
        (30.0, BmiCategory.OBESE_I),
        (34.9, BmiCategory.OBESE_I),
        (35.0, BmiCategory.OBESE_II),
        (39.9, BmiCategory.OBESE_II),
        (40.0, BmiCategory.OBESE_III),
        (50.0, BmiCategory.OBESE_III),
    ],
)
def test_bmi_category_boundaries(bmi_value, expected):
    assert bmi_category(bmi_value) == expected


def test_ideal_body_weight_male_at_base_height():
    assert ideal_body_weight_kg(152.4, Sex.MALE) == pytest.approx(50.0, abs=0.01)


def test_ideal_body_weight_female_at_base_height():
    assert ideal_body_weight_kg(152.4, Sex.FEMALE) == pytest.approx(45.5, abs=0.01)


def test_ideal_body_weight_below_base_height_does_not_go_negative():
    # Shorter than the 5ft base: no inches "over", so IBW == base, never negative.
    ibw = ideal_body_weight_kg(140.0, Sex.FEMALE)
    assert ibw == pytest.approx(45.5, abs=0.01)


def test_ideal_body_weight_scales_with_height():
    ibw_tall = ideal_body_weight_kg(180.0, Sex.MALE)
    ibw_base = ideal_body_weight_kg(152.4, Sex.MALE)
    assert ibw_tall > ibw_base


def test_adjusted_body_weight_between_ibw_and_actual_for_obese():
    # 120kg at 170cm is obese; ABW should sit between IBW and actual weight.
    ibw = ideal_body_weight_kg(170.0, Sex.MALE)
    abw = adjusted_body_weight_kg(120.0, 170.0, Sex.MALE)
    assert ibw < abw < 120.0


def test_adjusted_body_weight_equals_actual_when_at_ibw():
    ibw = ideal_body_weight_kg(170.0, Sex.MALE)
    abw = adjusted_body_weight_kg(ibw, 170.0, Sex.MALE)
    assert abw == pytest.approx(ibw, abs=0.01)
