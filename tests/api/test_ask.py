"""Tests for the legacy /ask endpoint, replacing the old test_api.py (which
had zero assertions, required a live server, and spent real OpenAI money).
OpenAI and Pinecone are mocked — no network, no cost.

These specifically pin down the two Phase 0 bug fixes:
  - a 404 "no relevant document" must stay a 404 with its own message, not
    get re-wrapped as "Errore API OpenAI: 404: ..." by the generic handler.
  - an unexpected internal exception must not leak its message text to the
    client.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


@pytest.fixture(autouse=True)
def configured_settings(monkeypatch):
    from app.config import get_settings

    get_settings.cache_clear()
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_API_KEY", "test-key")
    monkeypatch.setenv("PINECONE_INDEX_NAME", "test-index")
    yield
    get_settings.cache_clear()


def _mock_openai_with_answer(answer: str | None = "Ecco la risposta."):
    client_mock = MagicMock()
    client_mock.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.0] * 1024)]
    )
    client_mock.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=answer))]
    )
    return client_mock


def _mock_pinecone_index(matches):
    index_mock = MagicMock()
    index_mock.query.return_value = SimpleNamespace(matches=matches)
    return index_mock


def test_ask_happy_path(monkeypatch):
    from app import clients

    clients.get_openai_client.cache_clear()
    clients.get_pinecone_index.cache_clear()
    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai_with_answer())
    monkeypatch.setattr(
        clients,
        "get_pinecone_index",
        lambda: _mock_pinecone_index([SimpleNamespace(metadata={"text": "Il fabbisogno proteico è..."})]),
    )

    r = client.post("/ask", json={"question": "Quante proteine devo mangiare?"})
    assert r.status_code == 200
    assert r.json()["answer"] == "Ecco la risposta."


def test_ask_no_relevant_documents_returns_404_with_own_message(monkeypatch):
    from app import clients

    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai_with_answer())
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([]))

    r = client.post("/ask", json={"question": "Chi ha vinto il mondiale 2006?"})
    assert r.status_code == 404
    # Must NOT be mislabeled as an OpenAI error by the generic handler.
    assert "OpenAI" not in r.json()["detail"]
    assert "documento" in r.json()["detail"].lower() or "document" in r.json()["detail"].lower()


def test_ask_internal_error_does_not_leak_exception_text(monkeypatch):
    from app import clients

    def boom():
        raise RuntimeError("super secret internal detail: sk-do-not-leak-this")

    monkeypatch.setattr(clients, "get_openai_client", boom)
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([]))

    r = client.post("/ask", json={"question": "ciao"})
    assert r.status_code == 500
    assert "sk-do-not-leak-this" not in r.text
    assert "request_id" in r.json()["detail"] or "request_id=" in r.json()["detail"]


def test_ask_empty_model_response_returns_502_not_silent_none(monkeypatch):
    from app import clients

    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai_with_answer(answer=None))
    monkeypatch.setattr(
        clients,
        "get_pinecone_index",
        lambda: _mock_pinecone_index([SimpleNamespace(metadata={"text": "context"})]),
    )

    r = client.post("/ask", json={"question": "ciao"})
    assert r.status_code == 502


def test_ask_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()

    r = client.post("/ask", json={"question": "ciao"})
    assert r.status_code == 503
    get_settings.cache_clear()


def test_ask_rejects_empty_question():
    r = client.post("/ask", json={"question": ""})
    assert r.status_code == 422


def test_ask_rejects_oversized_question():
    r = client.post("/ask", json={"question": "a" * 5000})
    assert r.status_code == 422


def test_ask_accepts_zero_age_without_dropping_it(monkeypatch):
    # Regression test for the truthiness bug: `if user_data.age:` used to
    # silently drop age=0 (and weight=0, height=0). Confirmed here by
    # checking the user context actually gets built into the prompt sent
    # to the model.
    from app import clients
    from app.api.routes.ask import UserData, _build_user_context

    ctx = _build_user_context(UserData(age=0, weight=0, height=0))
    assert "Età: 0 anni" in ctx
    assert "Peso: 0.0 kg" in ctx
    assert "Altezza: 0.0 cm" in ctx
