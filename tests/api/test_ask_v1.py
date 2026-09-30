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


def _mock_openai(answer="Il fabbisogno proteico è descritto in [1].", score=0.9):
    mock = MagicMock()
    mock.embeddings.create.return_value = SimpleNamespace(
        data=[SimpleNamespace(embedding=[0.0] * 1024)]
    )
    mock.chat.completions.create.return_value = SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=answer))]
    )
    return mock


def _mock_pinecone_index(matches):
    index = MagicMock()
    index.query.return_value = SimpleNamespace(matches=matches)
    return index


def _match(score, text="Il fabbisogno proteico giornaliero è di circa 0.9g/kg.", **extra):
    metadata = {"text": text, "doc_id": "crea-2018", "source_title": "Linee Guida", "page_start": 12, "page_end": 12}
    metadata.update(extra)
    return SimpleNamespace(score=score, metadata=metadata)


def test_ask_v1_grounded_answer_with_citations(monkeypatch):
    from app import clients

    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai())
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([_match(0.85)]))

    r = client.post("/v1/ask", json={"question": "Quante proteine devo mangiare?", "locale": "it"})
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is True
    assert len(body["citations"]) == 1
    assert body["citations"][0]["doc_id"] == "crea-2018"
    assert "[1]" in body["answer"]
    assert body["disclaimer"]


def test_ask_v1_below_threshold_never_calls_llm(monkeypatch):
    from app import clients

    chat_spy = MagicMock()

    def spy_openai():
        m = _mock_openai()
        m.chat.completions.create = chat_spy
        return m

    monkeypatch.setattr(clients, "get_openai_client", spy_openai)
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([_match(0.1)]))

    r = client.post("/v1/ask", json={"question": "Chi ha vinto il mondiale 2006?", "locale": "it"})
    assert r.status_code == 200
    body = r.json()
    assert body["grounded"] is False
    assert body["citations"] == []
    chat_spy.assert_not_called()


def test_ask_v1_below_threshold_returns_localized_not_in_sources(monkeypatch):
    from app import clients

    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai())
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([_match(0.1)]))

    r = client.post("/v1/ask", json={"question": "random", "locale": "en"})
    body = r.json()
    assert "sources" in body["answer"].lower() or "confidence" in body["answer"].lower()


def test_ask_v1_no_matches_at_all_returns_not_in_sources(monkeypatch):
    from app import clients

    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai())
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([]))

    r = client.post("/v1/ask", json={"question": "qualsiasi cosa", "locale": "it"})
    body = r.json()
    assert body["grounded"] is False


def test_ask_v1_strips_out_of_range_citation_markers(monkeypatch):
    from app import clients

    monkeypatch.setattr(
        clients, "get_openai_client", lambda: _mock_openai(answer="Vedi [1] e anche [7].")
    )
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([_match(0.85)]))

    r = client.post("/v1/ask", json={"question": "domanda", "locale": "it"})
    body = r.json()
    assert "[1]" in body["answer"]
    assert "[7]" not in body["answer"]


def test_ask_v1_rejects_empty_question():
    r = client.post("/v1/ask", json={"question": "", "locale": "it"})
    assert r.status_code == 422


def test_ask_v1_not_configured_returns_503(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    from app.config import get_settings

    get_settings.cache_clear()
    r = client.post("/v1/ask", json={"question": "ciao", "locale": "it"})
    assert r.status_code == 503
    get_settings.cache_clear()


def test_ask_v1_empty_model_response_returns_502(monkeypatch):
    from app import clients

    monkeypatch.setattr(clients, "get_openai_client", lambda: _mock_openai(answer=None))
    monkeypatch.setattr(clients, "get_pinecone_index", lambda: _mock_pinecone_index([_match(0.85)]))

    r = client.post("/v1/ask", json={"question": "domanda", "locale": "it"})
    assert r.status_code == 502
