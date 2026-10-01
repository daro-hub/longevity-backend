from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_alternatives_returns_similar_foods():
    r = client.post("/v1/plan/alternatives", json={"food_key": "petto_di_pollo_cotto", "n": 3})
    assert r.status_code == 200
    body = r.json()
    assert len(body["alternatives"]) == 3
    assert all("name" in a and "food_key" in a for a in body["alternatives"])


def test_alternatives_no_llm_call_needed(monkeypatch):
    # Spy on get_openai_client to prove it's never touched by this route.
    from app import clients

    spy = __import__("unittest.mock", fromlist=["MagicMock"]).MagicMock()
    monkeypatch.setattr(clients, "get_openai_client", spy)

    r = client.post("/v1/plan/alternatives", json={"food_key": "banana", "n": 2})
    assert r.status_code == 200
    spy.assert_not_called()


def test_alternatives_respects_exclude_tags():
    r = client.post(
        "/v1/plan/alternatives",
        json={"food_key": "merluzzo_cotto", "excluded_tags": ["fish"], "n": 5},
    )
    body = r.json()
    assert all("fish" not in a["tags"] for a in body["alternatives"])


def test_alternatives_unknown_food_key_returns_empty_list():
    r = client.post("/v1/plan/alternatives", json={"food_key": "does_not_exist"})
    assert r.status_code == 200
    assert r.json()["alternatives"] == []


def test_alternatives_n_out_of_range_rejected():
    r = client.post("/v1/plan/alternatives", json={"food_key": "banana", "n": 0})
    assert r.status_code == 422
