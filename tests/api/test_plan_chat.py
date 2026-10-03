from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.llm.intent import ChatIntent, ChatOperation
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
                    {"food_key": "petto_di_pollo_cotto", "grams": 200, "note": ""},
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


def make_intent(**overrides):
    defaults = dict(
        operation=ChatOperation.CLARIFY,
        scope_kind="item",
        day_index=-1,
        meal_index=-1,
        item_index=-1,
        selection=[],
        target_food_key="",
        instruction="",
        clarification_question="",
    )
    defaults.update(overrides)
    return ChatIntent(**defaults)


def _payload(message):
    return {**VALID_PROFILE, "plan": CURRENT_PLAN, "message": message}


def test_chat_refused_profile_never_calls_llm(monkeypatch):
    spy = MagicMock()
    monkeypatch.setattr("app.clients.get_openai_client", spy)

    r = client.post("/v1/plan/chat", json={**_payload("qualsiasi"), "age_years": 15})
    assert r.status_code == 200
    assert r.json()["refused"] is True
    spy.assert_not_called()


def test_chat_clarify_returns_question_without_touching_plan(monkeypatch):
    fake_openai = MagicMock()
    intent = make_intent(
        operation=ChatOperation.CLARIFY, clarification_question="Quale alimento intendi esattamente?"
    )

    class FakeIntentClient:
        def __init__(self, c):
            pass

        def parse(self, *a, **k):
            return intent

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIIntentClient", FakeIntentClient)

    r = client.post("/v1/plan/chat", json=_payload("cambialo"))
    body = r.json()
    assert body["reply"] == "Quale alimento intendi esattamente?"
    assert body["plan"] is None
    assert body["plan_status"] is None


def test_chat_get_alternatives_no_plan_mutation(monkeypatch):
    fake_openai = MagicMock()
    intent = make_intent(operation=ChatOperation.GET_ALTERNATIVES, target_food_key="petto_di_pollo_cotto")

    class FakeIntentClient:
        def __init__(self, c):
            pass

        def parse(self, *a, **k):
            return intent

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIIntentClient", FakeIntentClient)

    r = client.post("/v1/plan/chat", json=_payload("cosa posso usare al posto del pollo?"))
    body = r.json()
    assert body["plan"] is None
    assert body["alternatives"] is not None
    assert len(body["alternatives"]) > 0
    assert body["plan_status"] is None


def test_chat_regenerate_scope_swaps_the_item(monkeypatch):
    fake_openai = MagicMock()
    intent = make_intent(
        operation=ChatOperation.REGENERATE_SCOPE,
        scope_kind="item",
        day_index=0,
        meal_index=0,
        item_index=1,
        instruction="sostituisci con salmone",
    )

    class FakeIntentClient:
        def __init__(self, c):
            pass

        def parse(self, *a, **k):
            return intent

    class FakePlanClient:
        def __init__(self, c):
            pass

        def generate_partial(self, *a, **k):
            return PartialPlanDraft(items=[PlanItemDraft(food_key="salmone_cotto", grams=200, note="")])

        def repair_partial(self, *a, **k):
            return PartialPlanDraft(items=[PlanItemDraft(food_key="salmone_cotto", grams=250, note="")])

        def create_plan(self, *a, **k):
            raise NotImplementedError

        def repair_plan(self, *a, **k):
            raise NotImplementedError

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIIntentClient", FakeIntentClient)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", FakePlanClient)

    r = client.post("/v1/plan/chat", json=_payload("sostituisci il pollo con il salmone"))
    body = r.json()
    assert body["plan_status"] in ("ok", "repaired", "targets_only")
    if body["plan"] is not None:
        assert body["plan"]["days"][0]["meals"][0]["items"][1]["food_key"] == "salmone_cotto"
        assert body["plan"]["days"][0]["meals"][0]["items"][0]["food_key"] == "riso_bianco_cotto"
    assert body["reply"]


def test_chat_regenerate_full_structural_request(monkeypatch):
    fake_openai = MagicMock()
    intent = make_intent(
        operation=ChatOperation.REGENERATE_FULL, instruction="un solo pasto al giorno"
    )

    class FakeIntentClient:
        def __init__(self, c):
            pass

        def parse(self, *a, **k):
            return intent

    from app.llm.schemas import DayDraft, MealDraft, MealPlanDraft, MealSlot

    draft = MealPlanDraft(
        days=[
            DayDraft(
                meals=[
                    MealDraft(
                        slot=MealSlot.LUNCH,
                        items=[PlanItemDraft(food_key="riso_bianco_cotto", grams=400, note="")],
                    )
                ]
            )
        ]
    )

    class FakePlanClient:
        def __init__(self, c):
            pass

        def create_plan(self, system_prompt, catalogue, locale):
            assert "un solo pasto al giorno" in system_prompt
            return draft

        def repair_plan(self, *a, **k):
            return draft

        def generate_partial(self, *a, **k):
            raise NotImplementedError

        def repair_partial(self, *a, **k):
            raise NotImplementedError

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIIntentClient", FakeIntentClient)
    monkeypatch.setattr("app.api.routes.plan.OpenAIPlanClient", FakePlanClient)

    r = client.post("/v1/plan/chat", json=_payload("voglio fare un solo pasto al giorno"))
    assert r.status_code == 200
    body = r.json()
    assert body["plan_status"] in ("ok", "repaired", "targets_only")


def test_chat_intent_parse_exception_returns_graceful_reply(monkeypatch):
    fake_openai = MagicMock()

    class ExplodingIntentClient:
        def __init__(self, c):
            pass

        def parse(self, *a, **k):
            raise RuntimeError("boom")

    monkeypatch.setattr("app.clients.get_openai_client", lambda: fake_openai)
    monkeypatch.setattr("app.api.routes.plan.OpenAIIntentClient", ExplodingIntentClient)

    r = client.post("/v1/plan/chat", json=_payload("qualsiasi cosa"))
    assert r.status_code == 200
    body = r.json()
    assert body["reply"]
    assert body["plan"] is None


def test_chat_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post("/v1/plan/chat", json=_payload("qualsiasi"))
    assert r.status_code == 503
    get_settings.cache_clear()
