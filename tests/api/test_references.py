from fastapi.testclient import TestClient

from app.domain.references import REFERENCES
from app.main import app

client = TestClient(app)


def test_get_references_returns_full_registry():
    r = client.get("/v1/references")
    assert r.status_code == 200
    body = r.json()
    assert set(body.keys()) == set(REFERENCES.keys())
    for entry in body.values():
        assert entry["citation"]
