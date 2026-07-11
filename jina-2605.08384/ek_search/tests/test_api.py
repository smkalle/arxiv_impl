"""Iteration 2 — API endpoint tests."""
import pytest
from pathlib import Path
from fastapi.testclient import TestClient

SAMPLES_DIR = str(Path(__file__).parent.parent / "data" / "samples")


@pytest.fixture
def client(tmp_path):
    """TestClient with isolated tmp Chroma store and stub backend."""
    import os
    os.environ["EMBEDDING_BACKEND"] = "stub"
    os.environ["EMBED_DIM"] = "64"
    os.environ["CHROMA_PATH"] = str(tmp_path / "chroma")
    os.environ["CHROMA_COLLECTION"] = "test-api"

    from app.config import reset_settings
    reset_settings()

    from app.api import app, reset_singletons
    reset_singletons()

    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["backend"] == "stub"
    assert "document_count" in data


def test_stats_empty(client):
    r = client.get("/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_chunks"] == 0


def test_ingest_filesystem(client):
    r = client.post("/ingest", json={
        "source": "filesystem",
        "path": SAMPLES_DIR,
    })
    assert r.status_code == 200
    data = r.json()
    assert data["status"] == "ok"
    assert data["ingested"] >= 5
    assert data["failed"] == 0


def test_ingest_bad_path(client):
    r = client.post("/ingest", json={
        "source": "filesystem",
        "path": "/nonexistent/path/xyz",
    })
    assert r.status_code == 404


def test_ingest_bad_source(client):
    r = client.post("/ingest", json={"source": "loom", "path": "/tmp"})
    assert r.status_code == 400


def test_search_requires_query(client):
    r = client.post("/search", json={"n_results": 5})
    assert r.status_code == 400


def test_search_after_ingest(client):
    # Ingest first
    client.post("/ingest", json={"source": "filesystem", "path": SAMPLES_DIR})
    # Then search
    r = client.post("/search", json={"query_text": "onboarding", "n_results": 5})
    assert r.status_code == 200
    data = r.json()
    assert "results" in data
    assert "query_latency_ms" in data
    assert data["backend_used"] == "stub"
    assert isinstance(data["results"], list)


def test_search_result_schema(client):
    client.post("/ingest", json={"source": "filesystem", "path": SAMPLES_DIR})
    r = client.post("/search", json={"query_text": "security", "n_results": 3})
    data = r.json()
    for result in data["results"]:
        assert "id" in result
        assert "score" in result
        assert "modality" in result
        assert "snippet" in result
        assert "asset_url" in result


def test_stats_after_ingest(client):
    client.post("/ingest", json={"source": "filesystem", "path": SAMPLES_DIR})
    r = client.get("/stats")
    data = r.json()
    assert data["total_chunks"] >= 5
    assert "by_modality" in data
    assert "by_source" in data


def test_corpus_after_ingest(client):
    client.post("/ingest", json={"source": "filesystem", "path": SAMPLES_DIR})
    r = client.get("/corpus")
    assert r.status_code == 200
    data = r.json()
    assert data["total_chunks"] >= 5
    assert data["document_count"] >= 5
    assert data["documents"]
    first = data["documents"][0]
    assert "document_id" in first
    assert "asset_url" in first
    assert "chunk_count" in first
    assert "chunks" in first


def test_search_idempotent_ingest(client):
    client.post("/ingest", json={"source": "filesystem", "path": SAMPLES_DIR})
    r1 = client.get("/stats")
    client.post("/ingest", json={"source": "filesystem", "path": SAMPLES_DIR})
    r2 = client.get("/stats")
    assert r1.json()["total_chunks"] == r2.json()["total_chunks"]


def test_dashboard_route(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
