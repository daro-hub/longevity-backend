from __future__ import annotations

import copy
import logging
import uuid

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from app.api.mappers import profile_in_to_domain, targets_result_to_response
from app.api.schemas import ProfileIn, TargetsOut, ViolationOut
from app.clients import get_openai_client
from app.config import get_settings
from app.domain.engine import compute_targets
from app.domain.food_db import load_food_db
from app.domain.messages import DISCLAIMER
from app.domain.substitutes import find_substitutes
from app.llm.intent import ChatOperation, intent_to_edit_scope, resolve_intent
from app.llm.openai_client import OpenAIPlanClient
from app.llm.openai_intent_client import OpenAIIntentClient
from app.llm.planner import PLAN_STATUS_TARGETS_ONLY, generate_plan, regenerate_scope
from app.llm.scope import EditScope, ScopeError

router = APIRouter()
logger = logging.getLogger("app.api.plan")

_FOOD_DB = None  # loaded lazily, cached at module scope


def _food_db():
    global _FOOD_DB
    if _FOOD_DB is None:
        _FOOD_DB = load_food_db()
    return _FOOD_DB


def _enrich_plan_with_names(plan_dict: dict | None, food_db: dict, locale: str) -> dict | None:
    """Adds a human-readable `name` to every item, resolved from the food
    database by locale. The LLM schema itself never carries a name field
    (or any other field beyond food_key/grams/note) -- this is a display
    enrichment applied server-side after generation, not something the
    model produces.
    """
    if plan_dict is None:
        return None
    enriched = copy.deepcopy(plan_dict)
    for day in enriched.get("days", []):
        for meal in day.get("meals", []):
            for item in meal.get("items", []):
                food = food_db.get(item["food_key"])
                item["name"] = food.name(locale) if food else item["food_key"]
    return enriched


class PlanRequest(ProfileIn):
    excluded_tags: list[str] = Field(
        default_factory=list,
        description="Allergen/diet tags to exclude, e.g. ['fish','nuts','vegan']",
    )


class PlanResponse(BaseModel):
    refused: bool
    plan_status: str | None
    targets: TargetsOut | None
    plan: dict | None
    violations: list[ViolationOut]
    disclaimer: str


@router.post("/v1/plan", response_model=PlanResponse)
async def post_plan(request: Request, body: PlanRequest) -> PlanResponse:
    settings = get_settings()
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    disclaimer = DISCLAIMER.get(body.locale, DISCLAIMER["it"])

    profile = profile_in_to_domain(body)
    targets_result = compute_targets(profile)

    if targets_result.refused:
        mapped = targets_result_to_response(targets_result, body.locale)
        return PlanResponse(
            refused=True,
            plan_status=None,
            targets=None,
            plan=None,
            violations=mapped.violations,
            disclaimer=disclaimer,
        )

    missing = settings.missing_required_for_ask()
    if missing:
        logger.error("plan.not_configured", extra={"missing": missing, "request_id": req_id})
        raise HTTPException(status_code=503, detail=f"Service not configured (request_id={req_id})")

    mapped = targets_result_to_response(targets_result, body.locale)

    try:
        llm_client = OpenAIPlanClient(get_openai_client())
        result = generate_plan(
            llm_client,
            targets_result.targets,
            _food_db(),
            tuple(body.excluded_tags),
            body.locale,
        )
    except Exception:
        logger.exception("plan.generation_failed", extra={"request_id": req_id})
        # Never a 500 for this route: the computed targets are still
        # correct and useful on their own even if plan generation blew up.
        return PlanResponse(
            refused=False,
            plan_status=PLAN_STATUS_TARGETS_ONLY,
            targets=mapped.targets,
            plan=None,
            violations=mapped.violations,
            disclaimer=disclaimer,
        )

    return PlanResponse(
        refused=False,
        plan_status=result.plan_status,
        targets=mapped.targets,
        plan=_enrich_plan_with_names(result.plan, _food_db(), body.locale),
        violations=mapped.violations,
        disclaimer=disclaimer,
    )


class AlternativesRequest(BaseModel):
    food_key: str
    excluded_tags: list[str] = Field(default_factory=list)
    require_tags: list[str] = Field(default_factory=list)
    locale: str = Field("it", pattern="^(it|en)$")
    n: int = Field(3, ge=1, le=10)


class AlternativeOut(BaseModel):
    food_key: str
    name: str
    tags: list[str]


class AlternativesResponse(BaseModel):
    alternatives: list[AlternativeOut]


@router.post("/v1/plan/alternatives", response_model=AlternativesResponse)
async def post_plan_alternatives(body: AlternativesRequest) -> AlternativesResponse:
    """No LLM involved: alternatives are the nearest foods in macro-density
    space (app.domain.substitutes), which is instant, free, and never
    wrong in the way an LLM suggestion could be -- it's a distance
    calculation over data already loaded in memory.
    """
    results = find_substitutes(
        body.food_key,
        _food_db(),
        exclude_tags=tuple(body.excluded_tags),
        require_tags=tuple(body.require_tags),
        n=body.n,
    )
    return AlternativesResponse(
        alternatives=[
            AlternativeOut(food_key=s.food.key, name=s.food.name(body.locale), tags=list(s.food.tags))
            for s in results
        ]
    )


class EditScopeIn(BaseModel):
    kind: str = Field(..., pattern="^(plan|day|meal|item|selection)$")
    day_index: int | None = None
    meal_index: int | None = None
    item_index: int | None = None
    positions: list[tuple[int, int, int]] = Field(default_factory=list)


class PlanEditRequest(ProfileIn):
    excluded_tags: list[str] = Field(default_factory=list)
    plan: dict
    scope: EditScopeIn
    instruction: str = Field(..., min_length=1, max_length=1000)


@router.post("/v1/plan/edit", response_model=PlanResponse)
async def post_plan_edit(request: Request, body: PlanEditRequest) -> PlanResponse:
    """Scoped edit: swap one ingredient, regenerate one meal/day, or an
    arbitrary multi-select -- see app.llm.planner.regenerate_scope. Every
    item NOT in scope is guaranteed unchanged; only the open positions are
    ever shown to or decided by the model.
    """
    settings = get_settings()
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    disclaimer = DISCLAIMER.get(body.locale, DISCLAIMER["it"])

    profile = profile_in_to_domain(body)
    targets_result = compute_targets(profile)

    if targets_result.refused:
        mapped = targets_result_to_response(targets_result, body.locale)
        return PlanResponse(
            refused=True, plan_status=None, targets=None, plan=None,
            violations=mapped.violations, disclaimer=disclaimer,
        )

    missing = settings.missing_required_for_ask()
    if missing:
        logger.error("plan_edit.not_configured", extra={"missing": missing, "request_id": req_id})
        raise HTTPException(status_code=503, detail=f"Service not configured (request_id={req_id})")

    mapped = targets_result_to_response(targets_result, body.locale)
    scope = EditScope(
        kind=body.scope.kind,
        day_index=body.scope.day_index,
        meal_index=body.scope.meal_index,
        item_index=body.scope.item_index,
        positions=tuple(tuple(p) for p in body.scope.positions),
    )

    try:
        llm_client = OpenAIPlanClient(get_openai_client())
        result = regenerate_scope(
            llm_client,
            body.plan,
            scope,
            body.instruction,
            targets_result.targets,
            _food_db(),
            tuple(body.excluded_tags),
            body.locale,
        )
    except ScopeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception:
        logger.exception("plan_edit.failed", extra={"request_id": req_id})
        return PlanResponse(
            refused=False, plan_status=PLAN_STATUS_TARGETS_ONLY, targets=mapped.targets,
            plan=None, violations=mapped.violations, disclaimer=disclaimer,
        )

    return PlanResponse(
        refused=False,
        plan_status=result.plan_status,
        targets=mapped.targets,
        plan=_enrich_plan_with_names(result.plan, _food_db(), body.locale),
        violations=mapped.violations,
        disclaimer=disclaimer,
    )


class PlanChatRequest(ProfileIn):
    excluded_tags: list[str] = Field(default_factory=list)
    plan: dict
    message: str = Field(..., min_length=1, max_length=1000)


class PlanChatResponse(BaseModel):
    refused: bool
    reply: str
    plan_status: str | None
    targets: TargetsOut | None
    plan: dict | None
    alternatives: list[AlternativeOut] | None
    violations: list[ViolationOut]
    disclaimer: str


def _status_reply(plan_status: str, locale: str) -> str:
    if locale == "en":
        return {
            "ok": "Done -- the change fits your targets.",
            "repaired": "Done -- I had to adjust the portions slightly to stay within your targets.",
            "targets_only": (
                "I couldn't make this change while still hitting your targets with enough "
                "precision, so I left the plan as it was."
            ),
        }.get(plan_status, "Done.")
    return {
        "ok": "Fatto — la modifica rispetta i tuoi target.",
        "repaired": "Fatto — ho dovuto aggiustare leggermente le porzioni per restare nei tuoi target.",
        "targets_only": (
            "Non sono riuscito a fare questa modifica rispettando i target con sufficiente "
            "precisione, quindi ho lasciato il piano com'era."
        ),
    }.get(plan_status, "Fatto.")


@router.post("/v1/plan/chat", response_model=PlanChatResponse)
async def post_plan_chat(request: Request, body: PlanChatRequest) -> PlanChatResponse:
    """Natural-language front end: turns a free-text request about the
    current plan into one of (regenerate a scope, regenerate the whole
    structure, suggest alternatives, ask for clarification) via
    app.llm.intent, then executes it through the exact same validated
    mechanisms /v1/plan and /v1/plan/edit use -- nothing about how a
    request arrives changes how safely it's executed.
    """
    settings = get_settings()
    req_id = request.headers.get("x-request-id") or str(uuid.uuid4())
    disclaimer = DISCLAIMER.get(body.locale, DISCLAIMER["it"])

    profile = profile_in_to_domain(body)
    targets_result = compute_targets(profile)

    if targets_result.refused:
        mapped = targets_result_to_response(targets_result, body.locale)
        return PlanChatResponse(
            refused=True, reply="", plan_status=None, targets=None, plan=None,
            alternatives=None, violations=mapped.violations, disclaimer=disclaimer,
        )

    missing = settings.missing_required_for_ask()
    if missing:
        logger.error("plan_chat.not_configured", extra={"missing": missing, "request_id": req_id})
        raise HTTPException(status_code=503, detail=f"Service not configured (request_id={req_id})")

    mapped = targets_result_to_response(targets_result, body.locale)
    excluded_tags = tuple(body.excluded_tags)

    try:
        openai_client = get_openai_client()
        intent_client = OpenAIIntentClient(openai_client)
        intent = resolve_intent(intent_client, body.plan, body.message, body.locale)
    except Exception:
        logger.exception("plan_chat.intent_parse_failed", extra={"request_id": req_id})
        fallback = (
            "Sorry, I couldn't understand that request."
            if body.locale == "en"
            else "Mi dispiace, non sono riuscito a capire questa richiesta."
        )
        return PlanChatResponse(
            refused=False, reply=fallback, plan_status=None, targets=mapped.targets,
            plan=None, alternatives=None, violations=mapped.violations, disclaimer=disclaimer,
        )

    if intent.operation == ChatOperation.CLARIFY:
        return PlanChatResponse(
            refused=False, reply=intent.clarification_question, plan_status=None,
            targets=mapped.targets, plan=None, alternatives=None,
            violations=mapped.violations, disclaimer=disclaimer,
        )

    if intent.operation == ChatOperation.GET_ALTERNATIVES:
        subs = find_substitutes(intent.target_food_key, _food_db(), exclude_tags=excluded_tags, n=3)
        alternatives = [
            AlternativeOut(food_key=s.food.key, name=s.food.name(body.locale), tags=list(s.food.tags))
            for s in subs
        ]
        if alternatives:
            names = ", ".join(a.name for a in alternatives)
            reply = (
                f"You could use: {names}." if body.locale == "en" else f"Potresti usare: {names}."
            )
        else:
            reply = (
                "I couldn't find a good alternative for that."
                if body.locale == "en"
                else "Non ho trovato una buona alternativa per questo alimento."
            )
        return PlanChatResponse(
            refused=False, reply=reply, plan_status=None, targets=mapped.targets, plan=None,
            alternatives=alternatives, violations=mapped.violations, disclaimer=disclaimer,
        )

    try:
        plan_client = OpenAIPlanClient(openai_client)
        if intent.operation == ChatOperation.REGENERATE_FULL:
            result = generate_plan(
                plan_client, targets_result.targets, _food_db(), excluded_tags, body.locale,
                extra_instruction=intent.instruction,
            )
        else:  # REGENERATE_SCOPE
            scope = intent_to_edit_scope(intent)
            result = regenerate_scope(
                plan_client, body.plan, scope, intent.instruction, targets_result.targets,
                _food_db(), excluded_tags, body.locale,
            )
    except ScopeError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    except Exception:
        logger.exception("plan_chat.execution_failed", extra={"request_id": req_id})
        return PlanChatResponse(
            refused=False, reply=_status_reply(PLAN_STATUS_TARGETS_ONLY, body.locale),
            plan_status=PLAN_STATUS_TARGETS_ONLY, targets=mapped.targets, plan=None,
            alternatives=None, violations=mapped.violations, disclaimer=disclaimer,
        )

    return PlanChatResponse(
        refused=False,
        reply=_status_reply(result.plan_status, body.locale),
        plan_status=result.plan_status,
        targets=mapped.targets,
        plan=_enrich_plan_with_names(result.plan, _food_db(), body.locale),
        alternatives=None,
        violations=mapped.violations,
        disclaimer=disclaimer,
    )
