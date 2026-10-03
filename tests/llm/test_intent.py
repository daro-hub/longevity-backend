import pytest

from app.llm.intent import (
    ChatIntent,
    ChatOperation,
    describe_plan,
    intent_to_edit_scope,
    resolve_intent,
)
from app.llm.scope import EditScope, ScopeError


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
            }
        ]
    }


def make_intent(**overrides):
    defaults = dict(
        operation=ChatOperation.CLARIFY,
        scope_kind="item",
        day_index=-1,
        meal_index=-1,
        item_index=-1,
        selection=[],
        target_food_key="",
        instruction="",
        clarification_question="",
    )
    defaults.update(overrides)
    return ChatIntent(**defaults)


def test_describe_plan_lists_every_position_it():
    desc = describe_plan(make_plan(), "it")
    assert "giorno=0 pasto=0 item=0" in desc
    assert "giorno=0 pasto=1 item=1" in desc
    assert "petto_di_pollo_cotto" in desc


def test_describe_plan_lists_every_position_en():
    desc = describe_plan(make_plan(), "en")
    assert "day=0 meal=1 item=1" in desc


def test_intent_to_edit_scope_plan():
    intent = make_intent(scope_kind="plan")
    assert intent_to_edit_scope(intent) == EditScope(kind="plan")


def test_intent_to_edit_scope_day():
    intent = make_intent(scope_kind="day", day_index=0)
    assert intent_to_edit_scope(intent) == EditScope(kind="day", day_index=0)


def test_intent_to_edit_scope_meal():
    intent = make_intent(scope_kind="meal", day_index=0, meal_index=1)
    assert intent_to_edit_scope(intent) == EditScope(kind="meal", day_index=0, meal_index=1)


def test_intent_to_edit_scope_item():
    intent = make_intent(scope_kind="item", day_index=0, meal_index=1, item_index=1)
    assert intent_to_edit_scope(intent) == EditScope(kind="item", day_index=0, meal_index=1, item_index=1)


def test_intent_to_edit_scope_selection():
    intent = make_intent(scope_kind="selection", selection=[[0, 0, 0], [0, 1, 1]])
    scope = intent_to_edit_scope(intent)
    assert scope.kind == "selection"
    assert scope.positions == ((0, 0, 0), (0, 1, 1))


def test_intent_to_edit_scope_unknown_kind_raises():
    intent = make_intent(scope_kind="nonsense")
    with pytest.raises(ScopeError):
        intent_to_edit_scope(intent)


def test_edit_scope_from_intent_is_usable_against_the_real_plan():
    # Round-trip: the scope converted from an intent must actually resolve
    # against the plan it was derived from.
    from app.llm.scope import open_positions

    plan = make_plan()
    intent = make_intent(scope_kind="item", day_index=0, meal_index=1, item_index=1)
    scope = intent_to_edit_scope(intent)
    assert open_positions(plan, scope) == {(0, 1, 1)}


class FakeIntentClient:
    def __init__(self, intent: ChatIntent):
        self._intent = intent
        self.last_call = None

    def parse(self, system_prompt, plan_description, message, locale):
        self.last_call = (system_prompt, plan_description, message, locale)
        return self._intent


def test_resolve_intent_passes_plan_description_and_message_through():
    plan = make_plan()
    intent = make_intent(operation=ChatOperation.GET_ALTERNATIVES, target_food_key="petto_di_pollo_cotto")
    client = FakeIntentClient(intent)

    result = resolve_intent(client, plan, "cosa posso usare al posto del pollo?", "it")

    assert result.operation == ChatOperation.GET_ALTERNATIVES
    assert result.target_food_key == "petto_di_pollo_cotto"
    system_prompt, plan_description, message, locale = client.last_call
    assert "petto_di_pollo_cotto" in plan_description
    assert message == "cosa posso usare al posto del pollo?"
    assert locale == "it"
    assert "regenerate_scope" in system_prompt
