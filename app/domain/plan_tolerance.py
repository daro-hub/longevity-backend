"""Shared tolerance-checking logic, used by both plan_fitting.py (the pure,
no-LLM repair pass) and app.llm.validator (full validation with violation
codes for the LLM repair prompt). Kept in one place so the two never drift
apart on what "close enough" means.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import references as ref
from app.domain.models import MacroTargets
from app.domain.nutrition import PlanTotals


@dataclass(frozen=True)
class ToleranceCheck:
    kcal_ok: bool
    protein_ok: bool
    fat_ok: bool
    carb_ok: bool
    fiber_ok: bool
    kcal_delta: float  # totals - target, signed
    protein_delta: float
    fat_delta: float
    carb_delta: float
    fiber_delta: float

    @property
    def all_ok(self) -> bool:
        return self.kcal_ok and self.protein_ok and self.fat_ok and self.carb_ok and self.fiber_ok


def check_tolerance(totals: PlanTotals, target_kcal: float, macros: MacroTargets) -> ToleranceCheck:
    kcal_delta = totals.kcal - target_kcal
    kcal_band = max(ref.KCAL_TOLERANCE_PCT * target_kcal, ref.KCAL_TOLERANCE_MIN_ABS)
    kcal_ok = abs(kcal_delta) <= kcal_band

    protein_delta = totals.protein_g - macros.protein_g
    protein_ok = (
        protein_delta >= -ref.PROTEIN_TOLERANCE_UNDER_PCT * macros.protein_g
        and protein_delta <= ref.PROTEIN_TOLERANCE_OVER_PCT * macros.protein_g
    )

    fat_delta = totals.fat_g - macros.fat_g
    fat_ok = abs(fat_delta) <= ref.FAT_TOLERANCE_PCT * macros.fat_g

    carb_delta = totals.carb_g - macros.carb_g
    carb_ok = abs(carb_delta) <= ref.CARB_TOLERANCE_PCT * macros.carb_g

    fiber_delta = totals.fiber_g - macros.fiber_g
    fiber_ok = totals.fiber_g >= ref.FIBER_TOLERANCE_MIN_FRACTION * macros.fiber_g

    return ToleranceCheck(
        kcal_ok=kcal_ok,
        protein_ok=protein_ok,
        fat_ok=fat_ok,
        carb_ok=carb_ok,
        fiber_ok=fiber_ok,
        kcal_delta=kcal_delta,
        protein_delta=protein_delta,
        fat_delta=fat_delta,
        carb_delta=carb_delta,
        fiber_delta=fiber_delta,
    )
