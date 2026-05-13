from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from sira_kb_ingestor.errors import RetrievalError
from sira_kb_ingestor.retriever import Retriever


class _FakeSiraModule:
    def __init__(self, response: dict | None = None, load_error: Exception | None = None) -> None:
        self._index = SimpleNamespace(articles=[{"article_id": "KB-1"}, {"article_id": "KB-2"}])
        self.response = response or {
            "results": [
                {
                    "article_id": "KB-1",
                    "title": "Authentication failure",
                    "snippet": "Auth service returned 503.",
                    "score": 7.5,
                    "matched_original_terms": ["login"],
                    "matched_enriched_terms": ["app crash"],
                }
            ],
            "sketch_terms_generated": ["auth service"],
            "sketch_terms_validated": ["auth service"],
            "sketch_terms_rejected": [],
            "fallback_used": False,
            "latency_ms": 12,
            "hallucination_rate": 0.0,
        }
        self.load_error = load_error
        self.loaded_path = None
        self.retrieve_args = None

    def load_index(self, path: Path) -> None:
        if self.load_error:
            raise self.load_error
        self.loaded_path = path

    def sira_retrieve(self, ticket_text: str, top_k: int, tau: float, w: float) -> dict:
        self.retrieve_args = (ticket_text, top_k, tau, w)
        return self.response


def test_retriever_health_reports_missing_index(tmp_path: Path) -> None:
    print("[TEST] Validating retriever health reports missing index")
    retriever = Retriever(tmp_path)
    health = retriever.health()
    assert health["bm25_index_loaded"] is False
    assert health["corpus_size"] == 0
    assert "not found" in health["load_error"]


def test_retriever_loads_index_and_reports_health(tmp_path: Path) -> None:
    print("[TEST] Validating retriever loads kb_index.pkl and reports corpus size")
    (tmp_path / "kb_index.pkl").write_text("fake-index", encoding="utf-8")
    fake = _FakeSiraModule()
    retriever = Retriever(tmp_path)
    retriever._sira_retrieve_module = fake
    retriever.load()

    health = retriever.health()
    assert health["bm25_index_loaded"] is True
    assert health["corpus_size"] == 2
    assert fake.loaded_path == tmp_path / "kb_index.pkl"


def test_retriever_maps_sira_response(tmp_path: Path) -> None:
    print("[TEST] Validating retriever maps SIRA response into integration contract")
    (tmp_path / "kb_index.pkl").write_text("fake-index", encoding="utf-8")
    fake = _FakeSiraModule()
    retriever = Retriever(tmp_path)
    retriever._sira_retrieve_module = fake
    retriever.load()

    response = retriever.retrieve("app fails login", top_k=3, tau=0.02, weight=2.0)

    assert response["kb_articles"][0]["id"] == "KB-1"
    assert response["kb_articles"][0]["matched_terms"] == ["login"]
    assert response["audit"]["sketch_terms_generated"] == ["auth service"]
    assert fake.retrieve_args == ("app fails login", 3, 0.02, 2.0)


def test_retriever_preserves_fallback_audit(tmp_path: Path) -> None:
    print("[TEST] Validating retriever preserves SIRA fallback audit")
    (tmp_path / "kb_index.pkl").write_text("fake-index", encoding="utf-8")
    fake = _FakeSiraModule(response={
        "results": [],
        "sketch_terms_generated": [],
        "sketch_terms_validated": [],
        "sketch_terms_rejected": [],
        "fallback_used": True,
        "latency_ms": 3,
        "hallucination_rate": 0.0,
    })
    retriever = Retriever(tmp_path)
    retriever._sira_retrieve_module = fake
    retriever.load()

    response = retriever.retrieve("ticket text")
    assert response["audit"]["fallback_used"] is True


def test_retriever_load_failure_raises_retrieval_error(tmp_path: Path) -> None:
    print("[TEST] Validating corrupt index load raises RetrievalError")
    (tmp_path / "kb_index.pkl").write_text("bad-index", encoding="utf-8")
    fake = _FakeSiraModule(load_error=ValueError("bad pickle"))
    retriever = Retriever(tmp_path)
    retriever._sira_retrieve_module = fake

    with pytest.raises(RetrievalError, match="Failed to load KB index"):
        retriever.load()
