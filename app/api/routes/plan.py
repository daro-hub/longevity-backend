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
from app.llm.openai_client import OpenAIPlanClient
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
