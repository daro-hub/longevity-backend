"""Food composition database loader.

Loads data/foods/foods.it.json and validates every row against the Atwater
identity at import time: if a row's stored kcal doesn't match
4*protein + 4*carb + 9*fat within FOOD_DB_ATWATER_TOLERANCE_PCT, it is
rejected rather than silently trusted. Skipping this check is how a couple
of bad rows make the plan validator (app.llm.validator) permanently
unsatisfiable for reasons that look like a prompt problem but are actually
a data problem — see the project plan.

This file is intentionally free of any tag-name assumptions beyond what's
declared in FoodItem — the actual tag vocabulary (vegan, fish, nuts, ...)
lives only in the JSON data and the caller's filtering logic
(see filter_foods).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from app.domain import references as ref

DEFAULT_FOOD_DB_PATH = Path(__file__).parent.parent.parent / "data" / "foods" / "foods.it.json"


@dataclass(frozen=True)
class FoodItem:
    key: str
    name_it: str
    name_en: str
    kcal: float
    protein_g: float
    carb_g: float
    fat_g: float
    fiber_g: float
    tags: tuple[str, ...]

    def name(self, locale: str) -> str:
        return self.name_en if locale == "en" else self.name_it


class FoodDbError(ValueError):
    pass


def _validate_row(row: dict) -> None:
    macros = row.get("per_100g", {})
    required = ("kcal", "protein_g", "carb_g", "fat_g", "fiber_g")
    missing = [f for f in required if f not in macros]
    if missing:
        raise FoodDbError(f"food '{row.get('key')}' missing fields: {missing}")

    recomputed = (
        ref.KCAL_PER_G_PROTEIN * macros["protein_g"]
        + ref.KCAL_PER_G_CARB * macros["carb_g"]
        + ref.KCAL_PER_G_FAT * macros["fat_g"]
    )
    stated = macros["kcal"]
    if stated <= 0:
        raise FoodDbError(f"food '{row.get('key')}' has non-positive kcal")

    deviation = abs(recomputed - stated) / stated
    if deviation > ref.FOOD_DB_ATWATER_TOLERANCE_PCT:
        raise FoodDbError(
            f"food '{row.get('key')}' fails Atwater check: stated kcal={stated}, "
            f"recomputed from macros={recomputed:.1f} ({deviation:.1%} deviation, "
            f"tolerance={ref.FOOD_DB_ATWATER_TOLERANCE_PCT:.0%})"
        )


def load_food_db(path: Path | None = None) -> dict[str, FoodItem]:
    """Returns a dict keyed by food `key`. Raises FoodDbError on any row
    that fails validation — the whole load fails loudly rather than
    silently dropping a bad row and going on.
    """
    db_path = path or DEFAULT_FOOD_DB_PATH
    with open(db_path, encoding="utf-8") as f:
        rows = json.load(f)

    items: dict[str, FoodItem] = {}
    for row in rows:
        _validate_row(row)
        key = row["key"]
        if key in items:
            raise FoodDbError(f"duplicate food key: {key}")
        macros = row["per_100g"]
        items[key] = FoodItem(
            key=key,
            name_it=row["name_it"],
            name_en=row["name_en"],
            kcal=macros["kcal"],
            protein_g=macros["protein_g"],
            carb_g=macros["carb_g"],
            fat_g=macros["fat_g"],
            fiber_g=macros["fiber_g"],
            tags=tuple(row.get("tags", [])),
        )
    return items


def filter_foods(
    foods: dict[str, FoodItem],
    exclude_tags: tuple[str, ...] = (),
    require_tags: tuple[str, ...] = (),
) -> dict[str, FoodItem]:
    """exclude_tags: allergens the food must NOT have (e.g. "nuts", "fish").
    require_tags: diet constraints the food MUST have (e.g. "vegan",
    "gluten_free") — a food needs ALL of these tags to pass.

    Filtering server-side, before the catalogue ever reaches the LLM, is
    deliberate: an excluded food should not even be offerable, rather than
    relying on a prompt instruction the model might not follow.
    """
    result = {}
    for key, item in foods.items():
        if any(tag in item.tags for tag in exclude_tags):
            continue
        if not all(tag in item.tags for tag in require_tags):
            continue
        result[key] = item
    return result
