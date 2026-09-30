from fastapi.testclient import TestClient

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
}


def test_post_targets_happy_path():
    r = client.post("/v1/targets", json=VALID_PROFILE)
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is False
    assert body["targets"]["bmi"] > 0
    assert body["targets"]["calories"]["kcal"] > 0
    assert body["targets"]["macros"]["protein_g"] > 0
    assert body["disclaimer"]


def test_post_targets_refused_for_minor():
    payload = {**VALID_PROFILE, "age_years": 15}
    r = client.post("/v1/targets", json=payload)
    assert r.status_code == 200
    body = r.json()
    assert body["refused"] is True
    assert body["targets"] is None
    codes = [v["code"] for v in body["violations"]]
    assert "AGE_MINOR" in codes


def test_post_targets_localizes_messages():
    payload = {**VALID_PROFILE, "age_years": 15, "locale": "en"}
    r = client.post("/v1/targets", json=payload)
    body = r.json()
    assert "minor" in body["violations"][0]["message"].lower() or "validated" in body["violations"][0]["message"].lower()


def test_post_targets_rejects_invalid_enum():
    payload = {**VALID_PROFILE, "activity_level": "super_active_nonsense"}
    r = client.post("/v1/targets", json=payload)
    assert r.status_code == 422


def test_post_targets_rejects_out_of_schema_age():
    payload = {**VALID_PROFILE, "age_years": -5}
    r = client.post("/v1/targets", json=payload)
    assert r.status_code == 422


def test_post_targets_warnings_present_for_elderly():
    payload = {**VALID_PROFILE, "age_years": 92}
    r = client.post("/v1/targets", json=payload)
    body = r.json()
    assert body["refused"] is False
    warning_codes = [w["code"] for w in body["targets"]["warnings"]]
    assert "AGE_ELDERLY" in warning_codes
