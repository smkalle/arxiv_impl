from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

import sira_kb_ingestor.api as api_module
from sira_kb_ingestor.api import create_app
from sira_kb_ingestor.errors import RetrievalError


class _FakeRetriever:
    def __init__(self, artifact_dir: Path | str = "./sira-artifacts", loaded: bool = True) -> None:
        self.artifact_dir = Path(artifact_dir)
        self.loaded = loaded

    def _try_load(self) -> bool:
        return self.loaded

    def health(self) -> dict:
        return {
            "bm25_index_loaded": self.loaded,
            "corpus_size": 2 if self.loaded else 0,
            "index_path": str(self.artifact_dir / "kb_index.pkl"),
            "index_built_at": "2026-05-13T00:00:00+00:00" if self.loaded else None,
            "load_error": None if self.loaded else "missing",
        }

    def retrieve(self, ticket_text: str, top_k: int = 5, tau: float = 0.01, weight: float = 1.5) -> dict:
        if not self.loaded:
            raise RetrievalError("KB index not loaded")
        fallback = "fallback" in ticket_text
        return {
            "kb_articles": [
                {
                    "id": "KB-1",
                    "title": "Auth",
                    "body": "Auth body",
                    "score": 4.2,
                    "matched_terms": ["login"],
                    "matched_enriched_terms": ["app crash"],
                }
            ],
            "audit": {
                "sketch_terms_generated": ["auth"],
                "sketch_terms_validated": ["auth"],
                "sketch_terms_rejected": [],
                "fallback_used": fallback,
                "latency_ms": 10,
                "hallucination_rate": 0.0,
            },
        }


def test_health_endpoint(monkeypatch) -> None:
    print("[TEST] Validating API health endpoint")
    monkeypatch.setattr(api_module, "Retriever", _FakeRetriever)
    client = TestClient(create_app("./artifacts"))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["bm25_index_loaded"] is True
    assert response.json()["corpus_size"] == 2


def test_retrieve_happy_path(monkeypatch) -> None:
    print("[TEST] Validating API retrieve happy path")
    monkeypatch.setattr(api_module, "Retriever", _FakeRetriever)
    client = TestClient(create_app("./artifacts"))

    response = client.post("/retrieve", json={"ticket_text": "login fails", "top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["kb_articles"][0]["id"] == "KB-1"
    assert payload["audit"]["fallback_used"] is False


def test_retrieve_missing_ticket_text_returns_400(monkeypatch) -> None:
    print("[TEST] Validating API retrieve rejects missing ticket_text")
    monkeypatch.setattr(api_module, "Retriever", _FakeRetriever)
    client = TestClient(create_app("./artifacts"))

    response = client.post("/retrieve", json={"top_k": 3})

    assert response.status_code == 400
    assert "ticket_text" in response.json()["detail"]


def test_retrieve_unavailable_index_returns_503(monkeypatch) -> None:
    print("[TEST] Validating API returns 503 when index is unavailable")
    class MissingRetriever(_FakeRetriever):
        def __init__(self, artifact_dir: Path | str = "./sira-artifacts") -> None:
            super().__init__(artifact_dir=artifact_dir, loaded=False)

    monkeypatch.setattr(api_module, "Retriever", MissingRetriever)
    client = TestClient(create_app("./artifacts"))

    response = client.post("/retrieve", json={"ticket_text": "login fails"})

    assert response.status_code == 503


def test_metrics_endpoint_tracks_success_and_fallback(monkeypatch) -> None:
    print("[TEST] Validating API metrics counters")
    monkeypatch.setattr(api_module, "Retriever", _FakeRetriever)
    client = TestClient(create_app("./artifacts"))

    client.post("/retrieve", json={"ticket_text": "login fails"})
    client.post("/retrieve", json={"ticket_text": "fallback please"})
    metrics = client.get("/metrics").json()

    assert metrics["total_requests"] == 2
    assert metrics["successful_requests"] == 2
    assert metrics["fallback_count"] == 1
    assert "average_latency_ms" in metrics
