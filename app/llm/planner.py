"""Orchestrates the generate -> validate -> repair loop.

    generate -> total_macros -> validate
      |- ok   -> done ("ok")
      \\- fail -> plan_fitting.fit_to_targets(...)      # PURE, no LLM
                   |- ok   -> done ("repaired")
                   \\- fail -> ONE LLM repair call -> total_macros -> validate
                                |- ok   -> done ("repaired")
                                \\- fail -> "targets_only"

Hard failures (unknown food_key, a banned tag, implausible grams) skip
straight to the LLM repair call rather than through plan_fitting — fitting
only scales/nudges existing grams, it cannot swap out a food the model
was never supposed to use in the first place.

At most one LLM repair call is ever made, for both cost and latency
reasons (this sits on top of an already-slow free-tier backend). When
repair still doesn't land within tolerance, the caller gets back the
computed targets (still correct and useful on their own) with
plan_status="targets_only" — never a 500, never a silently-broken plan.
"""

from __future__ import annotations

import copy
import logging
from dataclasses import dataclass
from typing import Protocol

from app.domain.food_db import FoodItem, filter_foods
from app.domain.models import Targets
from app.domain.nutrition import PlanTotals
from app.domain.plan_fitting import fit_to_targets
from app.llm.schemas import MealPlanDraft
from app.llm.validator import ValidationResult, validate

logger = logging.getLogger("app.llm.planner")

PLAN_STATUS_OK = "ok"
PLAN_STATUS_REPAIRED = "repaired"
PLAN_STATUS_TARGETS_ONLY = "targets_only"

_PROMPTS_DIR = None  # set lazily to avoid import-time filesystem access in tests


def _prompts_dir():
    global _PROMPTS_DIR
    if _PROMPTS_DIR is None:
        from pathlib import Path

        _PROMPTS_DIR = Path(__file__).parent / "prompts"
    return _PROMPTS_DIR


def _load_prompt(locale: str, targets: Targets) -> str:
    filename = "plan_en.md" if locale == "en" else "plan_it.md"
    template = (_prompts_dir() / filename).read_text(encoding="utf-8")
    return template.format(
        kcal=targets.calories.kcal,
        protein_g=targets.macros.protein_g,
        carb_g=targets.macros.carb_g,
        fat_g=targets.macros.fat_g,
        fiber_g=targets.macros.fiber_g,
    )


class LLMPlanClient(Protocol):
    """The narrow interface planner.py needs from an OpenAI-like client —
    narrow on purpose, so tests can pass a trivial fake instead of mocking
    the real SDK's object graph.
    """

    def create_plan(self, system_prompt: str, catalogue: list[dict], locale: str) -> MealPlanDraft: ...

    def repair_plan(
        self,
        system_prompt: str,
        catalogue: list[dict],
        previous_draft: MealPlanDraft,
        repair_note: str,
        locale: str,
    ) -> MealPlanDraft: ...


@dataclass(frozen=True)
class PlanResult:
    plan_status: str
    plan: dict | None
    totals: PlanTotals | None
    validation: ValidationResult | None
    hard_fail_reasons: tuple[str, ...] = ()


def _catalogue_payload(foods: dict[str, FoodItem], locale: str) -> list[dict]:
    # Deliberately NO macro fields here — see app.llm.schemas docstring.
    return [{"food_key": key, "name": item.name(locale), "tags": list(item.tags)} for key, item in foods.items()]


def _rebuild_plan_with_items(plan_dict: dict, items) -> dict:
    """Writes adjusted (food_key, grams) back into a deep copy of the
    original nested plan structure, in the same traversal order
    nutrition.flatten_plan_items used to produce `items`. Only valid when
    item count is unchanged (i.e. after plan_fitting, never after dropping
    hard-fail items).
    """
    new_plan = copy.deepcopy(plan_dict)
    it = iter(items)
    for day in new_plan.get("days", []):
        for meal in day.get("meals", []):
            for raw_item in meal.get("items", []):
                updated = next(it)
                raw_item["food_key"] = updated.food_key
                raw_item["grams"] = updated.grams
    return new_plan


def _build_repair_note(validation: ValidationResult, targets: Targets, locale: str) -> str:
    """The repair prompt's core: server-recomputed totals labeled as
    computed by the system (not the model), with signed deltas per
    nutrient. A bare "try again" regresses as often as it improves —
    this gives the model something concrete to act on.
    """
    if validation.hard_failed:
        reasons = "; ".join(validation.hard_fail_reasons)
        if locale == "en":
            return (
                f"Your previous plan had structural problems: {reasons}. "
                "Use only food_key values from the supplied catalogue, respect gram limits "
                "(1-1000g per item, max 2000g per meal), and never use an excluded food."
            )
        return (
            f"Il tuo piano precedente aveva problemi strutturali: {reasons}. "
            "Usa solo i food_key del catalogo fornito, rispetta i limiti di grammatura "
            "(1-1000g per alimento, massimo 2000g per pasto), e non usare mai un alimento escluso."
        )

    t = validation.tolerance
    totals = validation.totals
    if locale == "en":
        return (
            "These totals were computed by the SYSTEM from the items in your plan, not by you:\n"
            f"kcal={totals.kcal:.0f} (target {t.kcal_delta + totals.kcal:.0f}, delta {t.kcal_delta:+.0f}), "
            f"protein={totals.protein_g:.0f}g (delta {t.protein_delta:+.0f}g), "
            f"fat={totals.fat_g:.0f}g (delta {t.fat_delta:+.0f}g), "
            f"carb={totals.carb_g:.0f}g (delta {t.carb_delta:+.0f}g), "
            f"fiber={totals.fiber_g:.0f}g (delta {t.fiber_delta:+.0f}g).\n"
            "Adjust the grams of existing items where possible to close these deltas. "
            "You may add or remove at most 2 items. Do not change the meal structure."
        )
    return (
        "Questi totali sono stati calcolati dal SISTEMA a partire dagli alimenti del tuo piano, non da te:\n"
        f"kcal={totals.kcal:.0f} (target {t.kcal_delta + totals.kcal:.0f}, delta {t.kcal_delta:+.0f}), "
        f"proteine={totals.protein_g:.0f}g (delta {t.protein_delta:+.0f}g), "
        f"grassi={totals.fat_g:.0f}g (delta {t.fat_delta:+.0f}g), "
        f"carboidrati={totals.carb_g:.0f}g (delta {t.carb_delta:+.0f}g), "
        f"fibre={totals.fiber_g:.0f}g (delta {t.fiber_delta:+.0f}g).\n"
        "Aggiusta i grammi degli item esistenti dove possibile per chiudere questi delta. "
        "Puoi aggiungere o togliere al massimo 2 item. Non cambiare la struttura dei pasti."
    )


def generate_plan(
    llm_client: LLMPlanClient,
    targets: Targets,
    food_db: dict[str, FoodItem],
    excluded_tags: tuple[str, ...],
    locale: str,
) -> PlanResult:
    catalogue_foods = filter_foods(food_db, exclude_tags=excluded_tags)
    system_prompt = _load_prompt(locale, targets)
    catalogue = _catalogue_payload(catalogue_foods, locale)

    draft = llm_client.create_plan(system_prompt, catalogue, locale)
    plan_dict = draft.to_plain_dict()

    result = validate(plan_dict, targets.calories.kcal, targets.macros, food_db, excluded_tags)
    if result.ok:
        return PlanResult(PLAN_STATUS_OK, plan_dict, result.totals, result)

    if not result.hard_failed:
        # Structurally valid, just numerically off -- try the free fix first.
        fit = fit_to_targets(list(result.items), targets.calories.kcal, targets.macros, food_db)
        if fit.success:
            repaired_plan = _rebuild_plan_with_items(plan_dict, fit.items)
            revalidated = validate(repaired_plan, targets.calories.kcal, targets.macros, food_db, excluded_tags)
            return PlanResult(PLAN_STATUS_REPAIRED, repaired_plan, revalidated.totals, revalidated)

    # One LLM repair call, for either a hard fail or a fit_to_targets miss.
    repair_note = _build_repair_note(result, targets, locale)
    try:
        repaired_draft = llm_client.repair_plan(system_prompt, catalogue, draft, repair_note, locale)
    except Exception:
        logger.exception("planner.repair_call_failed")
        return PlanResult(PLAN_STATUS_TARGETS_ONLY, None, None, result, result.hard_fail_reasons)

    repaired_plan_dict = repaired_draft.to_plain_dict()
    final = validate(repaired_plan_dict, targets.calories.kcal, targets.macros, food_db, excluded_tags)
    if final.ok:
        return PlanResult(PLAN_STATUS_REPAIRED, repaired_plan_dict, final.totals, final)

    return PlanResult(PLAN_STATUS_TARGETS_ONLY, repaired_plan_dict, final.totals, final, final.hard_fail_reasons)
