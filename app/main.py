from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import ask, ask_v1, health, plan, references, targets
from app.config import get_settings
from app.logging_config import configure_logging

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(
    title="Longevity Backend",
    description="Nutrition targets engine + RAG-grounded Q&A",
    version="2.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS origins come from env now (settings.cors_allow_origins), not a
# hardcoded list with localhost ports baked into production. Credentials
# are disabled: auth uses bearer tokens, not cookies, so allow_credentials
# with allow_methods=["*"] was unnecessary attack surface.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router)
app.include_router(ask.router)  # legacy, unversioned — deleted once the frontend moves to /v1/ask
app.include_router(ask_v1.router)
app.include_router(targets.router)
app.include_router(plan.router)
app.include_router(references.router)
