"""Pure, no-LLM repair pass. Runs BEFORE any LLM retry in the plan
pipeline (app.llm.planner) because it's free and rescues most near-misses
— its real job is to reduce the model's task to "pick sensible foods for
these meals", leaving arithmetic entirely to this code.

Two passes, in order:
  1. proportional scaling of every item's grams toward the calorie target,
     clamped so it can't overcorrect a wildly wrong draft into something
     unrecognizable.
  2. a bounded greedy nudge: if protein is short, scale up the item with
     the highest protein density; if fat is over, scale down the item
     with the highest fat density. Repeated up to FIT_MAX_GREEDY_ITERATIONS
     times, stopping as soon as tolerance is met.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import references as ref
from app.domain.food_db import FoodItem
from app.domain.models import MacroTargets
from app.domain.nutrition import PlanItem, total_macros
from app.domain.plan_tolerance import check_tolerance
from app.domain.units import clamp


@dataclass(frozen=True)
class FitResult:
    items: list[PlanItem]
    success: bool
    iterations: int


def _clamp_grams(grams: float) -> float:
    return clamp(grams, ref.PLAN_ITEM_GRAMS_MIN, ref.PLAN_ITEM_GRAMS_MAX)


def _scale_items(items: list[PlanItem], factor: float) -> list[PlanItem]:
    return [PlanItem(food_key=i.food_key, grams=_clamp_grams(i.grams * factor)) for i in items]


def fit_to_targets(
    items: list[PlanItem],
    target_kcal: float,
    macros: MacroTargets,
    food_db: dict[str, FoodItem],
) -> FitResult:
    if not items:
        return FitResult(items=items, success=False, iterations=0)

    # Pass 1: proportional scaling toward the calorie target.
    totals = total_macros(items, food_db)
    if totals.kcal > 0:
        scale = clamp(target_kcal / totals.kcal, ref.FIT_SCALE_MIN, ref.FIT_SCALE_MAX)
        items = _scale_items(items, scale)

    totals = total_macros(items, food_db)
    check = check_tolerance(totals, target_kcal, macros)
    if check.all_ok:
        return FitResult(items=items, success=True, iterations=1)

    # Pass 2: bounded greedy nudge on protein/fat, in the direction that
    # doesn't fight pass 1's calorie scaling too much.
    for iteration in range(2, ref.FIT_MAX_GREEDY_ITERATIONS + 1):
        totals = total_macros(items, food_db)
        check = check_tolerance(totals, target_kcal, macros)
        if check.all_ok:
            return FitResult(items=items, success=True, iterations=iteration)

        # At most ONE nudge per iteration. Applying both a protein-up and a
        # fat-down nudge in the same pass caused them to fight each other
        # whenever the same item happened to be the extremum for both
        # (very common: many protein-dense foods are also fat-dense) —
        # the two adjustments partially cancelled out and the loop
        # oscillated without making progress. Protein goes first: its
        # tolerance band is asymmetric because undershooting it violates
        # a clinical floor, whereas the fat band is "clinically soft"
        # above its own floor (see references.PLAN_TOLERANCES_RATIONALE).
        adjusted = False

        if not check.protein_ok and check.protein_delta < 0:
            idx = _highest_density_index(items, food_db, "protein_g")
            if idx is not None:
                items = _nudge(items, idx, factor=1.10)
                adjusted = True
        elif not check.fat_ok and check.fat_delta > 0:
            idx = _highest_density_index(items, food_db, "fat_g")
            if idx is not None:
                items = _nudge(items, idx, factor=0.90)
                adjusted = True

        if not adjusted:
            break

    totals = total_macros(items, food_db)
    check = check_tolerance(totals, target_kcal, macros)
    return FitResult(items=items, success=check.all_ok, iterations=ref.FIT_MAX_GREEDY_ITERATIONS)


def _highest_density_index(
    items: list[PlanItem], food_db: dict[str, FoodItem], attr: str
) -> int | None:
    best_idx = None
    best_density = -1.0
    for idx, item in enumerate(items):
        food = food_db.get(item.food_key)
        if food is None:
            continue
        density = getattr(food, attr) / 100.0  # per gram
        if density > best_density:
            best_density = density
            best_idx = idx
    return best_idx


def _nudge(items: list[PlanItem], idx: int, factor: float) -> list[PlanItem]:
    new_items = list(items)
    target = new_items[idx]
    new_items[idx] = PlanItem(food_key=target.food_key, grams=_clamp_grams(target.grams * factor))
    return new_items
