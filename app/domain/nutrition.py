"""Sums macro totals for a meal plan's items against the food database.

This is the module that makes the whole "the LLM never invents a number"
design work: the model's output schema (app.llm.schemas.MealPlanDraft)
carries only `{food_key, grams}` per item — no calorie or macro field
anywhere. Every total in the system is computed HERE, in pure Python, from
the food database. The validator (app.llm.validator) is what checks a
food_key exists before calling this — total_macros itself assumes valid
keys and raises KeyError on a bad one, deliberately, since that check
belongs upstream.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.food_db import FoodItem


@dataclass(frozen=True)
class PlanItem:
    food_key: str
    grams: float


@dataclass(frozen=True)
class PlanTotals:
    kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float


def item_macros(item: PlanItem, food_db: dict[str, FoodItem]) -> PlanTotals:
    food = food_db[item.food_key]  # KeyError is deliberate — see module docstring
    factor = item.grams / 100.0
    return PlanTotals(
        kcal=food.kcal * factor,
        protein_g=food.protein_g * factor,
        carb_g=food.carb_g * factor,
        fat_g=food.fat_g * factor,
        fiber_g=food.fiber_g * factor,
    )


def total_macros(items: list[PlanItem], food_db: dict[str, FoodItem]) -> PlanTotals:
    kcal = protein = carb = fat = fiber = 0.0
    for item in items:
        m = item_macros(item, food_db)
        kcal += m.kcal
        protein += m.protein_g
        carb += m.carb_g
        fat += m.fat_g
        fiber += m.fiber_g
    return PlanTotals(kcal=kcal, protein_g=protein, carb_g=carb, fat_g=fat, fiber_g=fiber)


def flatten_plan_items(plan_dict: dict) -> list[PlanItem]:
    """Flattens the nested MealPlanDraft JSON shape
    ({days: [{meals: [{items: [{food_key, grams}]}]}]}) into a flat list.
    Takes a plain dict (not the pydantic model) so this stays usable from
    both the API layer and tests without importing app.llm here.
    """
    items: list[PlanItem] = []
    for day in plan_dict.get("days", []):
        for meal in day.get("meals", []):
            for raw_item in meal.get("items", []):
                items.append(PlanItem(food_key=raw_item["food_key"], grams=raw_item["grams"]))
    return items
