from types import SimpleNamespace

from fastapi.testclient import TestClient

import src.api as api_module
from src.retrieve import _set_index


def _mock_sira_response(fallback_used: bool = False) -> dict:
    return {
        "results": [
            {
                "article_id": "KB-001",
                "title": "Authentication service 503",
                "score": 9.42,
                "snippet": "Snippet...",
                "matched_original_terms": ["auth", "503"],
                "matched_enriched_terms": ["keeps crashing"],
            }
        ],
        "sketch_terms_generated": ["keeps crashing", "login loop"],
        "sketch_terms_validated": [] if fallback_used else ["keeps crashing"],
        "sketch_terms_rejected": ["login loop"] if not fallback_used else [],
        "fallback_used": fallback_used,
        "latency_ms": 42,
        "hallucination_rate": 0.5 if not fallback_used else 0.0,
    }


def test_retrieve_happy_path(monkeypatch):
    monkeypatch.setattr(api_module, "_try_load_index", lambda: True)
    monkeypatch.setattr(api_module.retrieve_module, "sira_retrieve", lambda *args, **kwargs: _mock_sira_response())

    client = TestClient(api_module.app)
    resp = client.post(
        "/retrieve",
        json={"ticket_id": "TKT-1", "ticket_text": "app keeps crashing"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "results" in data
    assert "sketch_terms_generated" in data
    assert "sketch_terms_validated" in data
    assert "sketch_terms_rejected" in data
    assert "fallback_used" in data
    assert "latency_ms" in data
    assert isinstance(data["latency_ms"], int)
    assert data["latency_ms"] > 0


def test_retrieve_fallback_true(monkeypatch):
    monkeypatch.setattr(api_module, "_try_load_index", lambda: True)
    monkeypatch.setattr(
        api_module.retrieve_module,
        "sira_retrieve",
        lambda *args, **kwargs: _mock_sira_response(fallback_used=True),
    )

    client = TestClient(api_module.app)
    resp = client.post(
        "/retrieve",
        json={"ticket_id": "TKT-2", "ticket_text": "app keeps crashing"},
    )
    assert resp.status_code == 200
    assert resp.json()["fallback_used"] is True


def test_retrieve_missing_ticket_text():
    client = TestClient(api_module.app)
    resp = client.post("/retrieve", json={"ticket_id": "TKT-3"})
    assert resp.status_code == 422


def test_retrieve_truncates_long_ticket(monkeypatch):
    monkeypatch.setattr(api_module, "_try_load_index", lambda: True)

    captured = {"text": None}

    def _fake_sira(text, top_k, w, tau):
        captured["text"] = text
        return _mock_sira_response()

    monkeypatch.setattr(api_module.retrieve_module, "sira_retrieve", _fake_sira)

    client = TestClient(api_module.app)
    long_text = "a" * 4500
    resp = client.post(
        "/retrieve",
        json={"ticket_id": "TKT-4", "ticket_text": long_text},
    )
    assert resp.status_code == 200
    assert len(captured["text"]) == 4000
    assert resp.json()["warning"] == "ticket_text truncated to 4000 characters"


def test_health_endpoint(monkeypatch):
    fake_index = SimpleNamespace(articles=[{"article_id": "KB-1"}], bm25=object())
    _set_index(fake_index)

    client = TestClient(api_module.app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["bm25_index_loaded"] is True
    assert data["corpus_size"] == 1
    assert "index_built_at" in data

    _set_index(None)


def test_feedback_endpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(api_module, "FEEDBACK_PATH", tmp_path / "feedback.jsonl")

    client = TestClient(api_module.app)
    resp = client.post(
        "/feedback",
        json={
            "ticket_id": "TKT-5",
            "selected_article_id": "KB-001",
            "rating": 5,
            "comments": "helpful",
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
