from __future__ import annotations

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
from app.llm.openai_client import OpenAIPlanClient
from app.llm.planner import PLAN_STATUS_TARGETS_ONLY, generate_plan

router = APIRouter()
logger = logging.getLogger("app.api.plan")

_FOOD_DB = None  # loaded lazily, cached at module scope


def _food_db():
    global _FOOD_DB
    if _FOOD_DB is None:
        _FOOD_DB = load_food_db()
    return _FOOD_DB


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
        plan=result.plan,
        violations=mapped.violations,
        disclaimer=disclaimer,
    )
