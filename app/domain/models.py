"""Data shapes for the domain engine. Plain dataclasses — no pydantic here,
so this package has zero framework dependency and can be imported by tests,
scripts, and the API layer alike.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.domain.enums import ActivityLevel, BmiCategory, Goal, Severity, Sex, ViolationCode


@dataclass(frozen=True)
class Profile:
    age_years: int
    sex: Sex
    height_cm: float
    weight_kg: float
    activity_level: ActivityLevel
    goal: Goal
    health_notes: str = ""  # free text, screened by guardrails.py


@dataclass(frozen=True)
class Violation:
    code: ViolationCode
    severity: Severity
    message_key: str  # key into app.domain.messages, resolved per locale
    params: dict = field(default_factory=dict)


@dataclass(frozen=True)
class CalorieTarget:
    kcal: float
    tdee_kcal: float
    bmr_kcal: float
    applied_adjustment_pct: float
    floor_applied: bool
    rationale_code: str | None = None


@dataclass(frozen=True)
class MacroTargets:
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float
    kcal_from_macros: float  # authoritative kcal target, recomputed from rounded grams


@dataclass(frozen=True)
class Targets:
    bmi: float
    bmi_category: BmiCategory
    calories: CalorieTarget
    macros: MacroTargets
    hydration_ml: float
    engine_version: str
    warnings: tuple[Violation, ...] = ()


@dataclass(frozen=True)
class TargetsResult:
    """Result of compute_targets: either usable Targets with warnings, or
    a refusal with no targets at all.
    """

    targets: Targets | None
    violations: tuple[Violation, ...]

    @property
    def refused(self) -> bool:
        return self.targets is None

    @property
    def plan_allowed(self) -> bool:
        """Whether a computed meal plan may be generated at all (distinct
        from whether *targets* were computed — AGE_MINOR blocks the plan
        even though it also blocks targets; some warn-level violations
        allow targets but should still be surfaced to the caller).
        """
        return not self.refused
