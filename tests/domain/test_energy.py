import pytest

from app.domain.energy import bmr_mifflin_st_jeor, calorie_target_for_adjustment, tdee
from app.domain.enums import ActivityLevel, Sex


def test_bmr_male_reference_case():
    # 30yo male, 80kg, 180cm: 10*80 + 6.25*180 - 5*30 + 5 = 800+1125-150+5 = 1780
    assert bmr_mifflin_st_jeor(80, 180, 30, Sex.MALE) == pytest.approx(1780.0)


def test_bmr_female_reference_case():
    # 30yo female, 65kg, 165cm: 10*65 + 6.25*165 - 5*30 - 161 = 650+1031.25-150-161 = 1370.25
    assert bmr_mifflin_st_jeor(65, 165, 30, Sex.FEMALE) == pytest.approx(1370.25)


def test_bmr_sex_offset_difference_is_166():
    # Same body, only sex differs: the constant gap between +5 and -161 is 166 kcal.
    male = bmr_mifflin_st_jeor(70, 170, 30, Sex.MALE)
    female = bmr_mifflin_st_jeor(70, 170, 30, Sex.FEMALE)
    assert (male - female) == pytest.approx(166.0)


@pytest.mark.parametrize(
    "activity,multiplier",
    [
        (ActivityLevel.SEDENTARY, 1.2),
        (ActivityLevel.LIGHT, 1.375),
        (ActivityLevel.MODERATE, 1.55),
        (ActivityLevel.ACTIVE, 1.725),
        (ActivityLevel.VERY_ACTIVE, 1.9),
    ],
)
def test_tdee_multipliers(activity, multiplier):
    assert tdee(1000.0, activity) == pytest.approx(1000.0 * multiplier)


def test_calorie_target_applies_adjustment():
    # tdee=2500, bmr=1500 (way below floor concerns), -20% -> 2000
    result = calorie_target_for_adjustment(2500.0, 1500.0, Sex.MALE, -0.20)
    assert result.kcal == pytest.approx(2000.0, abs=1)
    assert result.floor_applied is False


def test_calorie_target_bmr_relative_floor_applies():
    # tdee=1600, bmr=1550 -> -20% = 1280, but 1.1*bmr = 1705 > raw -> floor applies
    result = calorie_target_for_adjustment(1600.0, 1550.0, Sex.MALE, -0.20)
    assert result.floor_applied is True
    assert result.kcal == pytest.approx(1705.0, abs=1)


def test_calorie_target_absolute_floor_applies_for_small_body():
    # Very small BMR/TDEE with a large deficit should hit the absolute floor.
    result = calorie_target_for_adjustment(1300.0, 1100.0, Sex.FEMALE, -0.20)
    # -20% of 1300 = 1040; 1.1*1100=1210; absolute floor female=1200
    # floor = max(1210, 1200) = 1210
    assert result.floor_applied is True
    assert result.kcal == pytest.approx(1210.0, abs=1)


def test_calorie_target_no_adjustment_returns_tdee():
    result = calorie_target_for_adjustment(2200.0, 1600.0, Sex.MALE, 0.0)
    assert result.kcal == pytest.approx(2200.0, abs=1)
    assert result.floor_applied is False
