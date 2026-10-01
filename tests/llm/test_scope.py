import pytest

from app.llm.scope import (
    EditScope,
    ScopeError,
    all_positions,
    apply_partial,
    flat_index_map,
    open_positions,
)


def make_plan():
    return {
        "days": [
            {
                "meals": [
                    {"slot": "breakfast", "items": [{"food_key": "avena_fiocchi", "grams": 70}]},
                    {
                        "slot": "lunch",
                        "items": [
                            {"food_key": "riso_bianco_cotto", "grams": 250},
                            {"food_key": "petto_di_pollo_cotto", "grams": 200},
                        ],
                    },
                ]
            },
            {
                "meals": [
                    {"slot": "dinner", "items": [{"food_key": "merluzzo_cotto", "grams": 200}]},
                ]
            },
        ]
    }


def test_all_positions_lists_every_item_in_order():
    positions = all_positions(make_plan())
    assert positions == [(0, 0, 0), (0, 1, 0), (0, 1, 1), (1, 0, 0)]


def test_open_positions_plan_scope_is_everything():
    plan = make_plan()
    result = open_positions(plan, EditScope(kind="plan"))
    assert result == set(all_positions(plan))


def test_open_positions_day_scope():
    plan = make_plan()
    result = open_positions(plan, EditScope(kind="day", day_index=0))
    assert result == {(0, 0, 0), (0, 1, 0), (0, 1, 1)}


def test_open_positions_meal_scope():
    plan = make_plan()
    result = open_positions(plan, EditScope(kind="meal", day_index=0, meal_index=1))
    assert result == {(0, 1, 0), (0, 1, 1)}


def test_open_positions_item_scope():
    plan = make_plan()
    result = open_positions(plan, EditScope(kind="item", day_index=0, meal_index=1, item_index=1))
    assert result == {(0, 1, 1)}


def test_open_positions_item_scope_unknown_position_raises():
    plan = make_plan()
    with pytest.raises(ScopeError):
        open_positions(plan, EditScope(kind="item", day_index=5, meal_index=0, item_index=0))


def test_open_positions_selection_scope():
    plan = make_plan()
    result = open_positions(plan, EditScope(kind="selection", positions=((0, 0, 0), (1, 0, 0))))
    assert result == {(0, 0, 0), (1, 0, 0)}


def test_open_positions_selection_scope_unknown_raises():
    plan = make_plan()
    with pytest.raises(ScopeError):
        open_positions(plan, EditScope(kind="selection", positions=((9, 9, 9),)))


def test_open_positions_unknown_kind_raises():
    plan = make_plan()
    with pytest.raises(ScopeError):
        open_positions(plan, EditScope(kind="nonsense"))


def test_flat_index_map_matches_traversal_order():
    plan = make_plan()
    mapping = flat_index_map(plan)
    assert mapping[(0, 0, 0)] == 0
    assert mapping[(0, 1, 0)] == 1
    assert mapping[(0, 1, 1)] == 2
    assert mapping[(1, 0, 0)] == 3


def test_apply_partial_replaces_only_the_given_positions():
    plan = make_plan()
    merged = apply_partial(plan, [(0, 1, 1)], [{"food_key": "merluzzo_cotto", "grams": 180, "note": ""}])
    assert merged["days"][0]["meals"][1]["items"][1]["food_key"] == "merluzzo_cotto"
    # Everything else untouched.
    assert merged["days"][0]["meals"][1]["items"][0]["food_key"] == "riso_bianco_cotto"
    assert merged["days"][0]["meals"][0]["items"][0]["food_key"] == "avena_fiocchi"


def test_apply_partial_does_not_mutate_original():
    plan = make_plan()
    apply_partial(plan, [(0, 1, 1)], [{"food_key": "merluzzo_cotto", "grams": 180, "note": ""}])
    assert plan["days"][0]["meals"][1]["items"][1]["food_key"] == "petto_di_pollo_cotto"


def test_apply_partial_mismatched_count_raises():
    plan = make_plan()
    with pytest.raises(ScopeError):
        apply_partial(plan, [(0, 1, 1)], [])
