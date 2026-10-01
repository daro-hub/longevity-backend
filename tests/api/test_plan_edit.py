from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.llm.schemas import PartialPlanDraft, PlanItemDraft
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

CURRENT_PLAN = {
    "days": [
        {
            "meals": [
                {"slot": "lunch", "items": [
                    {"food_key": "riso_bianco_cotto", "grams": 250, "note": ""},
                    {"food_key": "merluzzo_cotto", "grams": 200, "note": ""},
                ]},
            ]
        }
    ]
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


class FakePartialClient:
    def __init__(self, *drafts):
        self._queue = list(drafts)

    def generate_partial(self, system_prompt, catalogue, context, locale):
        return self._queue.pop(0)

    def repair_partial(self, system_prompt, catalogue, context, previous_partial, repair_note, locale):
        return self._queue.pop(0)

    def create_plan(self, *a, **k):
        raise NotImplementedError

    def repair_plan(self, *a, **k):
        raise NotImplementedError


def _swap_draft():
    return PartialPlanDraft(items=[PlanItemDraft(food_key="salmone_cotto", grams=200, note="")])


def test_plan_edit_item_scope_swaps_only_that_item(monkeypatch):
    fake_openai = MagicMock()
    client_instance = FakePartialClient(_swap_draft(), _swap_draft())
    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", lambda c: client_instance)

    payload = {
        **VALID_PROFILE,
        "plan": CURRENT_PLAN,
        "scope": {"kind": "item", "day_index": 0, "meal_index": 0, "item_index": 1},
        "instruction": "sostituisci con salmone",
    }
    r = client.post("/v1/plan/edit", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is False
    if body["plan"] is not None:
        items = body["plan"]["days"][0]["meals"][0]["items"]
        assert items[1]["food_key"] == "salmone_cotto"
        assert items[0]["food_key"] == "riso_bianco_cotto"  # untouched


def test_plan_edit_refused_profile_never_calls_llm(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr("app.clients.get_openai_client", spy)

    payload = {
        **VALID_PROFILE,
        "age_years": 15,
        "plan": CURRENT_PLAN,
        "scope": {"kind": "item", "day_index": 0, "meal_index": 0, "item_index": 1},
        "instruction": "qualsiasi",
    }
    r = client.post("/v1/plan/edit", json=payload)
    assert r.status_code == 200
    assert r.json()["refused"] is True
    spy.assert_not_called()


def test_plan_edit_invalid_scope_returns_422(monkeypatch):
    fake_openai = MagicMock()
    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)

    payload = {
        **VALID_PROFILE,
        "plan": CURRENT_PLAN,
        "scope": {"kind": "item", "day_index": 9, "meal_index": 9, "item_index": 9},
        "instruction": "qualsiasi",
    }
    r = client.post("/v1/plan/edit", json=payload)
    assert r.status_code == 422


def test_plan_edit_exception_returns_targets_only(monkeypatch):
    fake_openai = MagicMock()

    class ExplodingClient:
        def generate_partial(self, *a, **k):
            raise RuntimeError("boom")

        def repair_partial(self, *a, **k):
            raise RuntimeError("boom")

        def create_plan(self, *a, **k):
            raise NotImplementedError

        def repair_plan(self, *a, **k):
            raise NotImplementedError

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", lambda c: ExplodingClient())

    payload = {
        **VALID_PROFILE,
        "plan": CURRENT_PLAN,
        "scope": {"kind": "item", "day_index": 0, "meal_index": 0, "item_index": 1},
        "instruction": "qualsiasi",
    }
    r = client.post("/v1/plan/edit", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["plan_status"] == "targets_only"
    assert body["targets"] is not None


def test_plan_edit_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    payload = {
        **VALID_PROFILE,
        "plan": CURRENT_PLAN,
        "scope": {"kind": "item", "day_index": 0, "meal_index": 0, "item_index": 1},
        "instruction": "qualsiasi",
    }
    r = client.post("/v1/plan/edit", json=payload)
    assert r.status_code == 503
    get_settings.cache_clear()
