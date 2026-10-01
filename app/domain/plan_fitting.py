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

`locked_indices` lets a caller mark some items as untouchable -- used by
scoped plan edits (app.llm.planner.regenerate_scope): if the user asked
to swap one ingredient, every OTHER item must come out of this function
bit-for-bit identical to how it went in. Locked items still count toward
the totals the open items are fit against; they're just never scaled or
nudged themselves.
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


def _scale_items(
    items: list[PlanItem], factor: float, locked_indices: frozenset[int] = frozenset()
) -> list[PlanItem]:
    return [
        i if idx in locked_indices else PlanItem(food_key=i.food_key, grams=_clamp_grams(i.grams * factor))
        for idx, i in enumerate(items)
    ]


def fit_to_targets(
    items: list[PlanItem],
    target_kcal: float,
    macros: MacroTargets,
    food_db: dict[str, FoodItem],
    locked_indices: frozenset[int] = frozenset(),
) -> FitResult:
    if not items:
        return FitResult(items=items, success=False, iterations=0)

    open_items_exist = any(idx not in locked_indices for idx in range(len(items)))
    if not open_items_exist:
        # Nothing is adjustable (e.g. a single-item scope that's itself
        # locked, which shouldn't happen in practice but must not crash).
        totals = total_macros(items, food_db)
        check = check_tolerance(totals, target_kcal, macros)
        return FitResult(items=items, success=check.all_ok, iterations=0)

    # Pass 1: proportional scaling toward the calorie target, applied only
    # to open items. Locked items' contribution is subtracted from the
    # target first, so the open items are scaled to make up the REMAINDER
    # rather than the whole target.
    totals = total_macros(items, food_db)
    locked_totals = total_macros([it for i, it in enumerate(items) if i in locked_indices], food_db)
    open_kcal = totals.kcal - locked_totals.kcal
    target_open_kcal = target_kcal - locked_totals.kcal
    if open_kcal > 0:
        scale = clamp(target_open_kcal / open_kcal, ref.FIT_SCALE_MIN, ref.FIT_SCALE_MAX)
        items = _scale_items(items, scale, locked_indices)

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
            idx = _highest_density_index(items, food_db, "protein_g", locked_indices)
            if idx is not None:
                items = _nudge(items, idx, factor=1.10)
                adjusted = True
        elif not check.fat_ok and check.fat_delta > 0:
            idx = _highest_density_index(items, food_db, "fat_g", locked_indices)
            if idx is not None:
                items = _nudge(items, idx, factor=0.90)
                adjusted = True

        if not adjusted:
            break

    totals = total_macros(items, food_db)
    check = check_tolerance(totals, target_kcal, macros)
    return FitResult(items=items, success=check.all_ok, iterations=ref.FIT_MAX_GREEDY_ITERATIONS)


def _highest_density_index(
    items: list[PlanItem],
    food_db: dict[str, FoodItem],
    attr: str,
    locked_indices: frozenset[int] = frozenset(),
) -> int | None:
    best_idx = None
    best_density = -1.0
    for idx, item in enumerate(items):
        if idx in locked_indices:
            continue
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
