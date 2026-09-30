"""Snapshot tests over tests/fixtures/golden_profiles.json.

These pin the exact numeric output of the engine for ~17 profiles covering
every guardrail branch and several BMI/goal combinations. Changing a
constant in references.py (say, the protein g/kg for lose_weight) will show
up here as a concrete, reviewable diff instead of silently changing
behavior — that's the point: it's a diff to look at and approve, not a
failure to "fix" by updating the fixture without reading it.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.domain.engine import compute_targets
from app.domain.enums import ActivityLevel, Goal, Sex
from app.domain.models import Profile

FIXTURE_PATH = Path(__file__).parent.parent / "fixtures" / "golden_profiles.json"


def _load_cases():
    with open(FIXTURE_PATH) as f:
        return json.load(f)


CASES = _load_cases()


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_golden_profile(case):
    inp = case["input"]
    profile = Profile(
        age_years=inp["age_years"],
        sex=Sex(inp["sex"]),
        height_cm=inp["height_cm"],
        weight_kg=inp["weight_kg"],
        activity_level=ActivityLevel(inp["activity_level"]),
        goal=Goal(inp["goal"]),
        health_notes=inp["health_notes"],
    )
    result = compute_targets(profile)
    expected = case["expected"]

    assert result.refused == expected["refused"]

    if expected["refused"]:
        actual_codes = sorted(v.code.value for v in result.violations)
        assert actual_codes == expected["violation_codes"]
        return

    t = result.targets
    assert t.bmi == pytest.approx(expected["bmi"], abs=0.05)
    assert t.bmi_category.value == expected["bmi_category"]
    assert t.calories.kcal == pytest.approx(expected["kcal"], abs=1)
    assert t.calories.applied_adjustment_pct == pytest.approx(expected["applied_adjustment_pct"])
    assert t.calories.floor_applied == expected["floor_applied"]
    assert t.macros.protein_g == pytest.approx(expected["protein_g"], abs=1)
    assert t.macros.carb_g == pytest.approx(expected["carb_g"], abs=1)
    assert t.macros.fat_g == pytest.approx(expected["fat_g"], abs=1)
    assert t.macros.fiber_g == pytest.approx(expected["fiber_g"], abs=1)
    assert t.hydration_ml == pytest.approx(expected["hydration_ml"], abs=1)
    assert sorted(v.code.value for v in t.warnings) == expected["warning_codes"]


def test_fixture_covers_every_refuse_violation_code():
    from app.domain.enums import Severity, ViolationCode

    refuse_codes = {
        ViolationCode.AGE_CHILD,
        ViolationCode.AGE_MINOR,
        ViolationCode.AGE_IMPLAUSIBLE,
        ViolationCode.HEIGHT_RANGE,
        ViolationCode.WEIGHT_RANGE,
        ViolationCode.BMI_SEVERE_UNDERWEIGHT,
        ViolationCode.CONDITION_SCREEN,
    }
    covered = set()
    for case in CASES:
        if case["expected"]["refused"]:
            covered.update(case["expected"]["violation_codes"])
    missing = {c.value for c in refuse_codes} - covered
    assert not missing, f"No golden fixture exercises: {missing}"
