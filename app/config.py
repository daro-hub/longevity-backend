"""Centralized settings via pydantic-settings.

Deliberately does NOT raise at import time. The old main.py did
`if not OPENAI_API_KEY: raise ValueError(...)` at module scope — on Render
that's a boot loop with no diagnosable startup error, not a clean 503.
Missing required settings are instead validated once in the app's lifespan
(app/main.py), which can log clearly and fail the health check instead of
crash-looping the process.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # OpenAI
    openai_api_key: str | None = None
    openai_chat_model: str = "gpt-4o-mini"
    openai_embedding_model: str = "text-embedding-3-small"
    openai_embedding_dimensions: int = 1024

    # Pinecone
    pinecone_api_key: str | None = None
    pinecone_index_name: str | None = None
    pinecone_namespace: str = ""

    # CORS — comma-separated origins. Defaults to the known frontend origins
    # so nothing breaks before this is configured, but production should
    # set this explicitly via env rather than relying on the default.
    cors_allow_origins: str = (
        "http://localhost:3000,http://localhost:3001,http://localhost:3002,"
        "https://longevity-alpha.vercel.app"
    )

    # Supabase (Phase 4 — auth). Optional until wired up; routes that need
    # auth will 501 rather than crash if these are unset.
    supabase_url: str | None = None
    supabase_project_ref: str | None = None
    supabase_jwt_audience: str = "authenticated"

    # Feature flags for staged rollout
    require_auth: bool = False

    log_level: str = "INFO"

    @property
    def cors_origins_list(self) -> list[str]:
        return [o.strip() for o in self.cors_allow_origins.split(",") if o.strip()]

    def missing_required_for_ask(self) -> list[str]:
        missing = []
        if not self.openai_api_key:
            missing.append("OPENAI_API_KEY")
        if not self.pinecone_api_key:
            missing.append("PINECONE_API_KEY")
        if not self.pinecone_index_name:
            missing.append("PINECONE_INDEX_NAME")
        return missing


@lru_cache
def get_settings() -> Settings:
    return Settings()
