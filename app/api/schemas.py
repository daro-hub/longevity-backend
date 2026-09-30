"""Pydantic request/response models for the v1 API. Separate from the
domain dataclasses in app.domain.models on purpose: the API schema is a
public contract (versioned, must stay backward compatible within v1) while
the domain models are free to change as the engine evolves.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from app.domain.enums import ActivityLevel, BmiCategory, Goal, Sex


class ProfileIn(BaseModel):
    age_years: int = Field(..., ge=0, le=150)
    sex: Sex
    height_cm: float = Field(..., gt=0)
    weight_kg: float = Field(..., gt=0)
    activity_level: ActivityLevel
    goal: Goal
    health_notes: str = Field("", max_length=2000)
    locale: str = Field("it", pattern="^(it|en)$")


class ViolationOut(BaseModel):
    code: str
    severity: str
    message: str


class CalorieTargetOut(BaseModel):
    kcal: float
    tdee_kcal: float
    bmr_kcal: float
    applied_adjustment_pct: float
    floor_applied: bool
    uncertainty_pct: float


class MacroTargetsOut(BaseModel):
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float
    kcal_from_macros: float


class TargetsOut(BaseModel):
    bmi: float
    bmi_category: BmiCategory
    calories: CalorieTargetOut
    macros: MacroTargetsOut
    hydration_ml: float
    engine_version: str
    warnings: list[ViolationOut]


class TargetsResponse(BaseModel):
    refused: bool
    targets: TargetsOut | None
    violations: list[ViolationOut]
    disclaimer: str
