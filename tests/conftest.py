"""Session-wide test isolation.

Tests must never depend on the contents of a developer's real .env file
-- this surfaced as a concrete bug, not a hypothetical: once a real .env
existed with placeholder text like `OPENAI_API_KEY=<INSERISCI_QUI>`,
pydantic-settings read that as a "present" (non-empty, truthy) value, so
missing_required_for_ask() stopped flagging it as missing whenever a test
deleted only the OS-level env var override. Disabling dotenv loading for
the whole test session makes tests hermetic regardless of what's sitting
in the repo's own .env.
"""

import pytest


@pytest.fixture(autouse=True, scope="session")
def _disable_dotenv_for_tests():
    from app.config import Settings

    Settings.model_config["env_file"] = None
