"""Iteration 3 — eval harness and golden pair tests."""
import json
import pytest
from pathlib import Path

GOLDEN_PATH = Path(__file__).parent.parent / "data" / "golden" / "golden_pairs.json"
SAMPLES_DIR = Path(__file__).parent.parent / "data" / "samples"


@pytest.fixture
def local_client(tmp_path):
    """TestClient with real local backend + real samples ingested."""
    import os
    os.environ["EMBEDDING_BACKEND"] = "local"
    os.environ["LOCAL_MODEL_ID"] = "all-MiniLM-L6-v2"
    os.environ["EMBED_DIM"] = "384"
    os.environ["CHROMA_PATH"] = str(tmp_path / "chroma")
    os.environ["CHROMA_COLLECTION"] = "eval-test"

    from app.config import reset_settings
    reset_settings()
    from app.api import app, reset_singletons
    reset_singletons()

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.post("/ingest", json={"source": "filesystem", "path": str(SAMPLES_DIR)})
        assert r.json()["ingested"] >= 5
        yield c


def test_golden_pairs_file_exists():
    assert GOLDEN_PATH.exists(), "Golden pairs file missing"


def test_golden_pairs_valid():
    pairs = json.loads(GOLDEN_PATH.read_text())
    assert len(pairs) >= 10
    for p in pairs:
        assert "id" in p
        assert "query_text" in p
        assert "expected_doc_ids" in p
        assert len(p["expected_doc_ids"]) >= 1


def test_eval_harness_runs(tmp_path):
    """EvalHarness runs without error on stub backend."""
    import os
    os.environ["EMBEDDING_BACKEND"] = "stub"
    os.environ["EMBED_DIM"] = "64"
    os.environ["CHROMA_PATH"] = str(tmp_path / "chroma")
    os.environ["CHROMA_COLLECTION"] = "harness-test"

    from app.config import reset_settings
    reset_settings()
    from app.api import app, reset_singletons
    reset_singletons()

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        c.post("/ingest", json={"source": "filesystem", "path": str(SAMPLES_DIR)})
        r = c.get("/eval")
    assert r.status_code == 200
    data = r.json()
    assert "precision_at_5" in data
    assert "mrr" in data
    assert data["total_queries"] == 10


@pytest.mark.slow
def test_golden_eval_local_backend(local_client):
    """Full golden eval with real embeddings.

    With a 7-doc / ~28-chunk corpus:
    - P@1 = 1.0 means every top-1 result is the correct document  → PASS
    - MRR  = 1.0 means first relevant result is always rank 1     → PASS
    - P@5 will be ~0.2-0.3 because slots 2-5 are occupied by other
      doc chunks; this is mathematically expected, not a bug.
    We gate on P@1 >= 0.80 and MRR >= 0.70 as meaningful signals.
    """
    r = local_client.get("/eval")
    assert r.status_code == 200
    report = r.json()

    print(f"\n=== Eval Report ===")
    print(f"P@1:  {report['precision_at_1']:.3f}   (gate: >= 0.80)")
    print(f"P@3:  {report['precision_at_3']:.3f}")
    print(f"P@5:  {report['precision_at_5']:.3f}   (informational — small corpus)")
    print(f"MRR:  {report['mrr']:.3f}   (gate: >= 0.70)")
    print(f"p50:  {report['latency_p50_ms']:.1f}ms")
    print(f"p95:  {report['latency_p95_ms']:.1f}ms  (gate: < 500ms)")

    # Primary gate: top-1 accuracy
    assert report["precision_at_1"] >= 0.80, \
        f"P@1 {report['precision_at_1']:.3f} below 0.80 — retrieval quality issue"

    # Primary gate: mean reciprocal rank
    assert report["mrr"] >= 0.70, \
        f"MRR {report['mrr']:.3f} below 0.70 — ranking quality issue"

    # Latency gate
    assert report["latency_p95_ms"] < 500, \
        f"p95 latency {report['latency_p95_ms']:.1f}ms exceeds 500ms"
