"""Validates a MealPlanDraft against targets and the food database.

Two tiers, checked in order:
  1. Hard failures — unknown food_key, a banned (allergen) tag present, or
     implausible grams. Allergens never get a "close enough": a banned
     tag is always a hard fail, never a tolerance question.
  2. Tolerance — once the plan is structurally valid, its (server-summed)
     totals are compared against the targets via
     app.domain.plan_tolerance.check_tolerance.

Nothing here trusts any number the model wrote — total_macros always
re-derives kcal/protein/carb/fat/fiber from food_key + grams against the
food database.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain import references as ref
from app.domain.food_db import FoodItem
from app.domain.models import MacroTargets
from app.domain.nutrition import PlanItem, PlanTotals, flatten_plan_items, total_macros
from app.domain.plan_tolerance import ToleranceCheck, check_tolerance


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    hard_fail_reasons: tuple[str, ...]
    items: tuple[PlanItem, ...]
    totals: PlanTotals | None
    tolerance: ToleranceCheck | None

    @property
    def hard_failed(self) -> bool:
        return bool(self.hard_fail_reasons)


def validate(
    plan_dict: dict,
    target_kcal: float,
    macros: MacroTargets,
    food_db: dict[str, FoodItem],
    excluded_tags: tuple[str, ...] = (),
) -> ValidationResult:
    items = flatten_plan_items(plan_dict)
    hard_fails: list[str] = []

    if not items:
        hard_fails.append("EMPTY_PLAN")
        return ValidationResult(
            ok=False, hard_fail_reasons=tuple(hard_fails), items=(), totals=None, tolerance=None
        )

    for item in items:
        food = food_db.get(item.food_key)
        if food is None:
            hard_fails.append(f"UNKNOWN_FOOD_KEY:{item.food_key}")
            continue
        if any(tag in food.tags for tag in excluded_tags):
            hard_fails.append(f"BANNED_TAG_PRESENT:{item.food_key}")
        if not (ref.PLAN_ITEM_GRAMS_MIN <= item.grams <= ref.PLAN_ITEM_GRAMS_MAX):
            hard_fails.append(f"GRAMS_OUT_OF_RANGE:{item.food_key}:{item.grams}")

    for day in plan_dict.get("days", []):
        for meal in day.get("meals", []):
            meal_grams = sum(i["grams"] for i in meal.get("items", []))
            if meal_grams > ref.PLAN_MEAL_GRAMS_MAX:
                hard_fails.append(f"MEAL_GRAMS_EXCEEDED:{meal.get('slot')}:{meal_grams}")

    if hard_fails:
        return ValidationResult(
            ok=False,
            hard_fail_reasons=tuple(hard_fails),
            items=tuple(items),
            totals=None,
            tolerance=None,
        )

    totals = total_macros(items, food_db)
    tolerance = check_tolerance(totals, target_kcal, macros)

    return ValidationResult(
        ok=tolerance.all_ok,
        hard_fail_reasons=(),
        items=tuple(items),
        totals=totals,
        tolerance=tolerance,
    )
