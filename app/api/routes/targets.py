from fastapi import APIRouter

from app.api.mappers import profile_in_to_domain, targets_result_to_response
from app.api.schemas import ProfileIn, TargetsResponse
from app.domain.engine import compute_targets

router = APIRouter()


@router.post("/v1/targets", response_model=TargetsResponse)
async def post_targets(profile_in: ProfileIn) -> TargetsResponse:
    """Compute deterministic nutrition targets (BMI, BMR, TDEE, calorie
    target, macro split, hydration) for a profile. No LLM call involved —
    every number here comes from app.domain, which is 100%-covered by
    unit tests and has a citation for every constant (see /v1/references).
    """
    profile = profile_in_to_domain(profile_in)
    result = compute_targets(profile)
    return targets_result_to_response(result, profile_in.locale)
