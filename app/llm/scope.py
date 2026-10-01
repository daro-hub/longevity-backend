"""Identifies which items in an existing plan are open to change vs
locked, for a scoped edit (swap one ingredient, regenerate one meal, one
day, or an arbitrary multi-select of the above). Every scope kind reduces
to the same thing: a set of (day_index, meal_index, item_index) positions.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class EditScope:
    kind: str  # "plan" | "day" | "meal" | "item" | "selection"
    day_index: int | None = None
    meal_index: int | None = None
    item_index: int | None = None
    positions: tuple[tuple[int, int, int], ...] = field(default_factory=tuple)


class ScopeError(ValueError):
    pass


def all_positions(plan_dict: dict) -> list[tuple[int, int, int]]:
    positions = []
    for d_idx, day in enumerate(plan_dict.get("days", [])):
        for m_idx, meal in enumerate(day.get("meals", [])):
            for i_idx in range(len(meal.get("items", []))):
                positions.append((d_idx, m_idx, i_idx))
    return positions


def open_positions(plan_dict: dict, scope: EditScope) -> set[tuple[int, int, int]]:
    everything = all_positions(plan_dict)

    if scope.kind == "plan":
        return set(everything)
    if scope.kind == "day":
        return {p for p in everything if p[0] == scope.day_index}
    if scope.kind == "meal":
        return {p for p in everything if p[0] == scope.day_index and p[1] == scope.meal_index}
    if scope.kind == "item":
        pos = (scope.day_index, scope.meal_index, scope.item_index)
        if pos not in set(everything):
            raise ScopeError(f"item position {pos} does not exist in this plan")
        return {pos}
    if scope.kind == "selection":
        unknown = set(scope.positions) - set(everything)
        if unknown:
            raise ScopeError(f"selection includes positions not in this plan: {unknown}")
        return set(scope.positions)

    raise ScopeError(f"unknown scope kind: {scope.kind!r}")


def flat_index_map(plan_dict: dict) -> dict[tuple[int, int, int], int]:
    """Maps each (day, meal, item) position to its index in the flat list
    nutrition.flatten_plan_items would produce -- same traversal order
    (days -> meals -> items), so locked_indices computed here line up
    exactly with the list fit_to_targets operates on.
    """
    return {pos: idx for idx, pos in enumerate(all_positions(plan_dict))}


def describe_item(plan_dict: dict, position: tuple[int, int, int]) -> dict:
    d_idx, m_idx, i_idx = position
    meal = plan_dict["days"][d_idx]["meals"][m_idx]
    item = meal["items"][i_idx]
    return {"slot": meal.get("slot"), "food_key": item.get("food_key"), "grams": item.get("grams")}


def apply_partial(
    plan_dict: dict, positions: list[tuple[int, int, int]], new_items: list[dict]
) -> dict:
    """Returns a deep copy of plan_dict with the items at `positions`
    replaced by `new_items`, matched 1:1 in the same (sorted) order.
    """
    import copy

    if len(positions) != len(new_items):
        raise ScopeError(
            f"expected {len(positions)} replacement item(s), model returned {len(new_items)}"
        )

    merged = copy.deepcopy(plan_dict)
    for (d_idx, m_idx, i_idx), new_item in zip(positions, new_items, strict=True):
        merged["days"][d_idx]["meals"][m_idx]["items"][i_idx] = dict(new_item)
    return merged
