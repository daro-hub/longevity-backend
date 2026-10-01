"""Food substitution suggestions. Deliberately has NO LLM involved: an
alternative is found by nearest-neighbor distance in macro-density space
(per 100g protein/carb/fat) over the food database, filtered by the same
exclude/require tags used everywhere else. This is instant, free, and
fully deterministic -- the same "don't trust the model with arithmetic"
principle extended to "don't even ask the model for this at all when a
simple distance calculation answers it better".
"""

from __future__ import annotations

from dataclasses import dataclass

from app.domain.food_db import FoodItem, filter_foods


@dataclass(frozen=True)
class Substitute:
    food: FoodItem
    distance: float  # lower = more similar macro profile per 100g


def _macro_distance(a: FoodItem, b: FoodItem) -> float:
    return (
        (a.protein_g - b.protein_g) ** 2 + (a.carb_g - b.carb_g) ** 2 + (a.fat_g - b.fat_g) ** 2
    ) ** 0.5


def find_substitutes(
    food_key: str,
    food_db: dict[str, FoodItem],
    exclude_tags: tuple[str, ...] = (),
    require_tags: tuple[str, ...] = (),
    n: int = 3,
) -> list[Substitute]:
    target = food_db.get(food_key)
    if target is None:
        return []

    candidates = filter_foods(food_db, exclude_tags=exclude_tags, require_tags=require_tags)
    candidates.pop(food_key, None)

    ranked = sorted(
        (Substitute(food=item, distance=_macro_distance(target, item)) for item in candidates.values()),
        key=lambda s: s.distance,
    )
    return ranked[:n]
