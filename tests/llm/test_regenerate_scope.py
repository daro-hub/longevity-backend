"""Tests the scoped-edit mechanism entirely with a fake in-memory client
-- no network. The contract under test: everything NOT in scope must
survive bit-for-bit identical, and the merged plan is validated/repaired
against the FULL targets (locked contribution + open contribution), never
just the open slice in isolation.
"""

from __future__ import annotations

import pytest

from app.domain.engine import compute_targets
from app.domain.enums import ActivityLevel, Goal, Sex
from app.domain.food_db import load_food_db
from app.domain.models import Profile
from app.llm.planner import (
    PLAN_STATUS_OK,
    PLAN_STATUS_REPAIRED,
    PLAN_STATUS_TARGETS_ONLY,
    regenerate_scope,
)
from app.llm.schemas import PartialPlanDraft, PlanItemDraft
from app.llm.scope import EditScope, ScopeError

DB = load_food_db()


def make_targets():
    profile = Profile(
        age_years=30,
        sex=Sex.MALE,
        height_cm=175.0,
        weight_kg=75.0,
        activity_level=ActivityLevel.MODERATE,
        goal=Goal.MAINTAIN,
    )
    return compute_targets(profile).targets


def make_current_plan():
    return {
        "days": [
            {
                "meals": [
                    {
                        "slot": "breakfast",
                        "items": [
                            {"food_key": "avena_fiocchi", "grams": 90, "note": ""},
                            {"food_key": "banana", "grams": 120, "note": ""},
                        ],
                    },
                    {
                        "slot": "lunch",
                        "items": [
                            {"food_key": "pasta_cotta", "grams": 350, "note": ""},
                            {"food_key": "petto_di_pollo_cotto", "grams": 220, "note": ""},
                            {"food_key": "olio_oliva", "grams": 15, "note": ""},
                        ],
                    },
                    {
                        "slot": "dinner",
                        "items": [
                            {"food_key": "riso_bianco_cotto", "grams": 300, "note": ""},
                            {"food_key": "merluzzo_cotto", "grams": 200, "note": ""},
                            {"food_key": "broccoli_cotti", "grams": 200, "note": ""},
                        ],
                    },
                ]
            }
        ]
    }


class FakePartialClient:
    def __init__(self, *partial_sequence):
        self._queue = list(partial_sequence)
        self.calls = []
        self.last_context = None

    def generate_partial(self, system_prompt, catalogue, context, locale):
        self.calls.append("generate_partial")
        self.last_context = context
        return self._queue.pop(0)

    def repair_partial(self, system_prompt, catalogue, context, previous_partial, repair_note, locale):
        self.calls.append("repair_partial")
        self.last_repair_note = repair_note
        return self._queue.pop(0)

    # Unused by regenerate_scope but part of the Protocol.
    def create_plan(self, *a, **k):
        raise NotImplementedError

    def repair_plan(self, *a, **k):
        raise NotImplementedError


def test_single_item_swap_leaves_everything_else_untouched():
    # This fixture plan is deliberately not pre-tuned to the profile's
    # real targets (carb is far short) -- a single swapped item often
    # can't close that gap alone, so this exercises the repair path too.
    # That's a legitimate thing to prove: whichever branch wins, the
    # locked items must survive bit-for-bit identical.
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="item", day_index=0, meal_index=2, item_index=1)  # dinner's merluzzo
    client = FakePartialClient(
        PartialPlanDraft(items=[PlanItemDraft(food_key="salmone_cotto", grams=180, note="")]),
        PartialPlanDraft(items=[PlanItemDraft(food_key="salmone_cotto", grams=250, note="")]),
    )

    result = regenerate_scope(client, plan, scope, "sostituisci con salmone", targets, DB, (), "it")

    assert result.plan is not None
    assert result.plan["days"][0]["meals"][2]["items"][1]["food_key"] == "salmone_cotto"
    # Every other item identical to the original, regardless of which
    # branch (first try or repair) produced the final plan.
    assert result.plan["days"][0]["meals"][0]["items"][0]["food_key"] == "avena_fiocchi"
    assert result.plan["days"][0]["meals"][0]["items"][0]["grams"] == 90
    assert result.plan["days"][0]["meals"][2]["items"][0]["food_key"] == "riso_bianco_cotto"
    assert result.plan["days"][0]["meals"][2]["items"][0]["grams"] == 300
    assert client.calls[0] == "generate_partial"


def test_meal_scope_regenerates_only_that_meals_items():
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="meal", day_index=0, meal_index=1)  # lunch, 3 items
    draft = PartialPlanDraft(
        items=[
            PlanItemDraft(food_key="quinoa_cotta", grams=200, note=""),
            PlanItemDraft(food_key="salmone_cotto", grams=180, note=""),
            PlanItemDraft(food_key="broccoli_cotti", grams=150, note=""),
        ]
    )
    client = FakePartialClient(draft, draft)  # same draft offered again if repair is needed

    result = regenerate_scope(client, plan, scope, "voglio qualcosa diverso a pranzo", targets, DB, (), "it")

    assert result.plan is not None
    lunch_items = result.plan["days"][0]["meals"][1]["items"]
    assert [i["food_key"] for i in lunch_items] == ["quinoa_cotta", "salmone_cotto", "broccoli_cotti"]
    # Breakfast and dinner untouched regardless of plan_status.
    assert result.plan["days"][0]["meals"][0]["items"][0]["food_key"] == "avena_fiocchi"
    assert result.plan["days"][0]["meals"][2]["items"][0]["food_key"] == "riso_bianco_cotto"


def test_result_is_validated_against_full_plan_not_just_open_slice():
    # The targets context carries the WHOLE day's targets. If the open
    # slot's replacement is wildly over target even accounting for the
    # locked items, it must not silently report "ok".
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="item", day_index=0, meal_index=1, item_index=2)  # the olive oil
    # Absurdly large oil swap -- should fail tolerance given everything else is locked.
    client = FakePartialClient(
        PartialPlanDraft(items=[PlanItemDraft(food_key="olio_oliva", grams=900, note="")]),
        PartialPlanDraft(items=[PlanItemDraft(food_key="olio_oliva", grams=15, note="")]),
    )

    result = regenerate_scope(client, plan, scope, "più olio", targets, DB, (), "it")

    assert result.plan_status in (PLAN_STATUS_REPAIRED, PLAN_STATUS_TARGETS_ONLY)
    assert "repair_partial" in client.calls


def test_item_count_mismatch_triggers_repair_not_crash():
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="meal", day_index=0, meal_index=0)  # breakfast, 2 items
    client = FakePartialClient(
        PartialPlanDraft(items=[PlanItemDraft(food_key="banana", grams=100, note="")]),  # only 1, expected 2
        PartialPlanDraft(
            items=[
                PlanItemDraft(food_key="avena_fiocchi", grams=90, note=""),
                PlanItemDraft(food_key="banana", grams=100, note=""),
            ]
        ),
    )

    result = regenerate_scope(client, plan, scope, "cambia la colazione", targets, DB, (), "it")

    assert client.calls == ["generate_partial", "repair_partial"]
    assert result.plan_status in (PLAN_STATUS_OK, PLAN_STATUS_REPAIRED, PLAN_STATUS_TARGETS_ONLY)


def test_repair_exception_falls_back_to_targets_only(monkeypatch):
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="item", day_index=0, meal_index=2, item_index=1)

    class ExplodingClient(FakePartialClient):
        def repair_partial(self, *a, **k):
            raise RuntimeError("network blew up")

    client = ExplodingClient(
        PartialPlanDraft(items=[PlanItemDraft(food_key="salmone_cotto", grams=5000, note="")])
    )
    # 5000g is out of PLAN_ITEM_GRAMS_MAX range -> hard fail -> repair attempted -> explodes.
    result = regenerate_scope(client, plan, scope, "tanto salmone", targets, DB, (), "it")
    assert result.plan_status == PLAN_STATUS_TARGETS_ONLY
    assert result.plan is None


def test_empty_scope_raises_scope_error():
    targets = make_targets()
    plan = {"days": [{"meals": [{"slot": "lunch", "items": []}]}]}
    client = FakePartialClient()
    with pytest.raises(ScopeError):
        regenerate_scope(client, plan, EditScope(kind="plan"), "qualsiasi", targets, DB, (), "it")


def test_day_scope_regenerates_all_meals_in_that_day():
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="day", day_index=0)
    # 2 + 3 + 3 = 8 items total in day 0
    draft = PartialPlanDraft(
        items=[
            PlanItemDraft(food_key="yogurt_greco_intero", grams=200, note=""),
            PlanItemDraft(food_key="mela", grams=100, note=""),
            PlanItemDraft(food_key="quinoa_cotta", grams=200, note=""),
            PlanItemDraft(food_key="petto_di_tacchino_cotto", grams=200, note=""),
            PlanItemDraft(food_key="olio_oliva", grams=10, note=""),
            PlanItemDraft(food_key="farro_cotto", grams=250, note=""),
            PlanItemDraft(food_key="orata_cotta", grams=200, note=""),
            PlanItemDraft(food_key="spinaci_cotti", grams=200, note=""),
        ]
    )
    client = FakePartialClient(draft, draft)

    result = regenerate_scope(client, plan, scope, "cambia tutta la giornata", targets, DB, (), "it")
    assert result.plan is not None
    all_items = [
        item["food_key"]
        for meal in result.plan["days"][0]["meals"]
        for item in meal["items"]
    ]
    assert all_items == [
        "yogurt_greco_intero", "mela", "quinoa_cotta", "petto_di_tacchino_cotto", "olio_oliva",
        "farro_cotto", "orata_cotta", "spinaci_cotti",
    ]


def test_excluded_tags_filter_the_catalogue_shown_to_the_model():
    targets = make_targets()
    plan = make_current_plan()
    scope = EditScope(kind="item", day_index=0, meal_index=2, item_index=1)

    seen_catalogues = []

    class RecordingClient(FakePartialClient):
        def generate_partial(self, system_prompt, catalogue, context, locale):
            seen_catalogues.append(catalogue)
            return super().generate_partial(system_prompt, catalogue, context, locale)

    client = RecordingClient(
        PartialPlanDraft(items=[PlanItemDraft(food_key="petto_di_pollo_cotto", grams=180, note="")])
    )
    regenerate_scope(client, plan, scope, "niente pesce", targets, DB, ("fish",), "it")
    keys = [item["food_key"] for item in seen_catalogues[0]]
    assert "salmone_cotto" not in keys
    assert "merluzzo_cotto" not in keys
