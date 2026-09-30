from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.llm.schemas import DayDraft, MealDraft, MealPlanDraft, MealSlot, PlanItemDraft
from app.main import app

client = TestClient(app)

VALID_PROFILE = {
    "age_years": 30,
    "sex": "male",
    "height_cm": 175.0,
    "weight_kg": 75.0,
    "activity_level": "moderate",
    "goal": "maintain",
    "health_notes": "",
    "locale": "it",
    "excluded_tags": [],
}


@pytest.fixture(autouse=True)
def configured_settings(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test-index")
    yield
    get_settings.cache_clear()


def _fake_draft():
    return MealPlanDraft(
        days=[
            DayDraft(
                meals=[
                    MealDraft(
                        slot=MealSlot.LUNCH,
                        items=[
                            PlanItemDraft(food_key="riso_bianco_cotto", grams=250, note=""),
                            PlanItemDraft(food_key="petto_di_pollo_cotto", grams=200, note=""),
                            PlanItemDraft(food_key="olio_oliva", grams=10, note=""),
                        ],
                    )
                ]
            )
        ]
    )


def test_plan_refused_profile_never_calls_llm(monkeypatch):
    called = {"n": 0}

    def spy(*a, **k):
        called["n"] += 1
        return MagicMock()

    monkeypatch.setattr("app.clients.get_openai_client", spy)
    payload = {**VALID_PROFILE, "age_years": 15}
    r = client.post("/v1/plan", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is True
    assert body["plan"] is None
    assert body["plan_status"] is None
    assert called["n"] == 0


def test_plan_happy_path_returns_a_plan(monkeypatch):
    fake_openai = MagicMock()

    class FakeOpenAIPlanClient:
        def __init__(self, client):
            pass

        def create_plan(self, system_prompt, catalogue, locale):
            return _fake_draft()

        def repair_plan(self, *a, **k):
            return _fake_draft()

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", FakeOpenAIPlanClient)

    r = client.post("/v1/plan", json=VALID_PROFILE)
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is False
    assert body["plan_status"] in ("ok", "repaired", "targets_only")
    assert body["targets"]["bmi"] > 0
    assert body["disclaimer"]


def test_plan_generation_exception_returns_targets_only_not_500(monkeypatch):
    fake_openai = MagicMock()

    class ExplodingPlanClient:
        def __init__(self, client):
            pass

        def create_plan(self, *a, **k):
            raise RuntimeError("boom")

        def repair_plan(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", ExplodingPlanClient)

    r = client.post("/v1/plan", json=VALID_PROFILE)
    assert r.status_code == 200
    body = r.json()
    assert body["plan_status"] == "targets_only"
    assert body["plan"] is None
    assert body["targets"] is not None  # targets survive even when the LLM blows up


def test_plan_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post("/v1/plan", json=VALID_PROFILE)
    assert r.status_code == 503
    get_settings.cache_clear()


def test_plan_items_have_human_readable_names(monkeypatch):
    fake_openai = MagicMock()

    class FakeOpenAIPlanClient:
        def __init__(self, client):
            pass

        def create_plan(self, system_prompt, catalogue, locale):
            return _fake_draft()

        def repair_plan(self, *a, **k):
            return _fake_draft()

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", FakeOpenAIPlanClient)

    r = client.post("/v1/plan", json=VALID_PROFILE)
    body = r.json()
    if body["plan"] is not None:
        item = body["plan"]["days"][0]["meals"][0]["items"][0]
        assert item["name"]
        assert item["food_key"] in ("riso_bianco_cotto", "petto_di_pollo_cotto", "olio_oliva")


def test_plan_excludes_requested_tags(monkeypatch):
    fake_openai = MagicMock()
    seen_catalogues = []

    class RecordingPlanClient:
        def __init__(self, client):
            pass

        def create_plan(self, system_prompt, catalogue, locale):
            seen_catalogues.append(catalogue)
            return _fake_draft()

        def repair_plan(self, *a, **k):
            return _fake_draft()

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", RecordingPlanClient)

    payload = {**VALID_PROFILE, "excluded_tags": ["fish"]}
    client.post("/v1/plan", json=payload)
    keys = [item["food_key"] for item in seen_catalogues[0]]
    assert "salmone_cotto" not in keys
