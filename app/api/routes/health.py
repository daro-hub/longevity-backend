from fastapi import APIRouter, Depends

from app.config import Settings, get_settings

router = APIRouter()


@router.get("/")
async def root(settings: Settings = Depends(get_settings)):
    """Health check. Deliberately reports which optional subsystems are
    configured instead of a hardcoded "ok" — the old version reported
    healthy even when OpenAI/Pinecone env vars were entirely missing,
    which made the endpoint useless for actually diagnosing a broken
    deploy.
    """
    missing = settings.missing_required_for_ask()
    return {
        "status": "ok",
        "message": "longevity backend is running",
        "ask_endpoint_ready": not missing,
        "missing_config": missing,
    }
