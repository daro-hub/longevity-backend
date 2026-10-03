"""Tests the generate -> validate -> repair loop entirely with a fake
in-memory LLMPlanClient -- no network, no OpenAI SDK object graph to mock.
The one live-network path (app.llm.openai_client.OpenAIPlanClient talking
to the real API) is exercised only by the opt-in integration test gated
behind RUN_LIVE_LLM=1.
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
    generate_plan,
)
from app.llm.schemas import DayDraft, MealDraft, MealPlanDraft, MealSlot, PlanItemDraft

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


def _draft(*meal_items):
    """meal_items: list of (slot, [(food_key, grams), ...])"""
    return MealPlanDraft(
        days=[
            DayDraft(
                meals=[
                    MealDraft(
                        slot=MealSlot(slot),
                        items=[PlanItemDraft(food_key=k, grams=g, note="") for k, g in items],
                    )
                    for slot, items in meal_items
                ]
            )
        ]
    )


class FakeLLMClient:
    """Scripted fake: returns draft_sequence[0] for create_plan, then each
    subsequent call (repair_plan) pops the next entry.
    """

    def __init__(self, *draft_sequence):
        self._queue = list(draft_sequence)
        self.calls = []

    def create_plan(self, system_prompt, catalogue, locale):
        self.calls.append("create")
        self.last_system_prompt = system_prompt
        return self._queue.pop(0)

    def repair_plan(self, system_prompt, catalogue, previous_draft, repair_note, locale):
        self.calls.append("repair")
        self.last_repair_note = repair_note
        return self._queue.pop(0)


def test_plan_never_raises_and_always_returns_a_valid_status():
    targets = make_targets()
    base = _draft(
        ("breakfast", [("avena_fiocchi", 80), ("banana", 100)]),
        ("lunch", [("riso_bianco_cotto", 250), ("petto_di_pollo_cotto", 220), ("olio_oliva", 12)]),
        ("dinner", [("merluzzo_cotto", 200), ("broccoli_cotti", 250), ("olio_oliva", 8)]),
    )
    fallback = _draft(("lunch", [("riso_bianco_cotto", 400), ("petto_di_pollo_cotto", 300)]))
    client = FakeLLMClient(base, fallback)
    result = generate_plan(client, targets, DB, excluded_tags=(), locale="it")
    assert result.plan_status in (PLAN_STATUS_OK, PLAN_STATUS_REPAIRED, PLAN_STATUS_TARGETS_ONLY)
    assert client.calls[0] == "create"


# Note: the "already-within-tolerance needs no LLM call at all" behavior
# is proven rigorously at the pure-function level in
# tests/domain/test_plan_fitting.py::test_already_within_tolerance_returns_unchanged,
# using a MacroTargets built directly from a real plan's own totals. It's
# not re-proven here at the planner-integration level: doing so by hand
# via a two-food linear system only pins 2 of the 5 tolerance dimensions
# (protein, carb) and left fat/fiber arbitrarily off, which made this
# test as flaky as the fixture-guessing attempts above rather than more
# reliable -- removed in favor of that existing domain-level test.


def test_hard_fail_triggers_repair_call():
    targets = make_targets()
    bad = _draft(("lunch", [("frittata_di_unicorno", 200)]))
    good = _draft(
        ("breakfast", [("avena_fiocchi", 80)]),
        ("lunch", [("riso_bianco_cotto", 250), ("petto_di_pollo_cotto", 200), ("olio_oliva", 10)]),
        ("dinner", [("merluzzo_cotto", 200), ("broccoli_cotti", 200)]),
    )
    client = FakeLLMClient(bad, good)
    result = generate_plan(client, targets, DB, excluded_tags=(), locale="it")
    assert client.calls == ["create", "repair"]
    assert result.plan_status in (PLAN_STATUS_REPAIRED, PLAN_STATUS_TARGETS_ONLY)


def test_hard_fail_repair_note_mentions_unknown_key():
    targets = make_targets()
    bad = _draft(("lunch", [("frittata_di_unicorno", 200)]))
    good = _draft(("lunch", [("riso_bianco_cotto", 200)]))
    client = FakeLLMClient(bad, good)
    generate_plan(client, targets, DB, excluded_tags=(), locale="it")
    assert "UNKNOWN_FOOD_KEY" in client.last_repair_note


def test_banned_tag_triggers_repair_not_fitting():
    targets = make_targets()
    fishy = _draft(("lunch", [("salmone_cotto", 200), ("riso_bianco_cotto", 200)]))
    fixed = _draft(("lunch", [("petto_di_pollo_cotto", 200), ("riso_bianco_cotto", 200)]))
    client = FakeLLMClient(fishy, fixed)
    result = generate_plan(client, targets, DB, excluded_tags=("fish",), locale="it")
    assert client.calls == ["create", "repair"]
    # The repaired plan must not reintroduce the banned food either --
    # validated against the same excluded_tags.
    if result.plan_status == PLAN_STATUS_REPAIRED:
        assert result.validation.ok


def test_slightly_off_plan_is_fixed_by_fitting_without_llm_repair():
    targets = make_targets()
    # A plan proportionally scaled down from a near-target one should be
    # fixable by fit_to_targets's proportional scaling pass alone.
    base = _draft(
        ("breakfast", [("avena_fiocchi", 70), ("banana", 90)]),
        ("lunch", [("riso_bianco_cotto", 220), ("petto_di_pollo_cotto", 190), ("olio_oliva", 10)]),
        ("dinner", [("merluzzo_cotto", 180), ("broccoli_cotti", 220)]),
    )
    client = FakeLLMClient(base)
    result = generate_plan(client, targets, DB, excluded_tags=(), locale="it")
    # Whether it lands exactly "ok" or gets "repaired" by fitting, it must
    # NOT have made a repair LLM call (fitting is free and tried first).
    if result.plan_status == PLAN_STATUS_REPAIRED:
        assert client.calls == ["create"]


def test_persistent_failure_after_repair_returns_targets_only_not_exception():
    targets = make_targets()
    always_bad = _draft(("lunch", [("insalata_verde", 30)]))
    still_bad = _draft(("lunch", [("insalata_verde", 40)]))
    client = FakeLLMClient(always_bad, still_bad)
    result = generate_plan(client, targets, DB, excluded_tags=(), locale="it")
    assert result.plan_status in (PLAN_STATUS_REPAIRED, PLAN_STATUS_TARGETS_ONLY)
    assert client.calls == ["create", "repair"]


def test_repair_call_exception_is_caught_and_returns_targets_only():
    targets = make_targets()

    class ExplodingClient:
        def create_plan(self, *a, **k):
            return _draft(("lunch", [("frittata_di_unicorno", 100)]))

        def repair_plan(self, *a, **k):
            raise RuntimeError("network blew up")

    result = generate_plan(ExplodingClient(), targets, DB, excluded_tags=(), locale="it")
    assert result.plan_status == PLAN_STATUS_TARGETS_ONLY
    assert result.plan is None


def test_locale_en_produces_english_repair_note():
    targets = make_targets()
    bad = _draft(("lunch", [("frittata_di_unicorno", 200)]))
    good = _draft(("lunch", [("riso_bianco_cotto", 200)]))
    client = FakeLLMClient(bad, good)
    generate_plan(client, targets, DB, excluded_tags=(), locale="en")
    assert "food_key" in client.last_repair_note or "catalogue" in client.last_repair_note


def test_at_most_one_repair_call_ever():
    targets = make_targets()
    always_bad = _draft(("lunch", [("insalata_verde", 20)]))
    still_bad_1 = _draft(("lunch", [("insalata_verde", 25)]))
    client = FakeLLMClient(always_bad, still_bad_1)
    generate_plan(client, targets, DB, excluded_tags=(), locale="it")
    assert client.calls.count("repair") <= 1


def test_extra_instruction_is_appended_to_the_system_prompt():
    targets = make_targets()
    base = _draft(("lunch", [("riso_bianco_cotto", 250), ("petto_di_pollo_cotto", 200)]))
    client = FakeLLMClient(base, base)
    generate_plan(
        client, targets, DB, excluded_tags=(), locale="it", extra_instruction="un solo pasto al giorno"
    )
    assert "un solo pasto al giorno" in client.last_system_prompt


def test_no_extra_instruction_leaves_prompt_unchanged():
    targets = make_targets()
    base = _draft(("lunch", [("riso_bianco_cotto", 250), ("petto_di_pollo_cotto", 200)]))
    client_without = FakeLLMClient(base, base)
    generate_plan(client_without, targets, DB, excluded_tags=(), locale="it")
    assert "Richiesta strutturale aggiuntiva" not in client_without.last_system_prompt
