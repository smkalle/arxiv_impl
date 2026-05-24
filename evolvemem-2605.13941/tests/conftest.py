"""Shared fixtures for all EvolveMem tests."""
import json
import sys
import tempfile
from pathlib import Path

import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))


@pytest.fixture
def tmp_data(tmp_path):
    """A temporary data directory with all required subdirs."""
    (tmp_path / "raw").mkdir()
    (tmp_path / "lancedb").mkdir()
    (tmp_path / "loop_states").mkdir()
    (tmp_path / "evolved").mkdir()
    return tmp_path


@pytest.fixture
def stub_router(tmp_data):
    """A seeded StubSimpleMemRouter with 5 IT support articles."""
    from simplemem_router_stub import StubSimpleMemRouter
    r = StubSimpleMemRouter(lancedb_uri=str(tmp_data / "lancedb")).create("text")
    articles = [
        ("app crashes on login after password change", "Auth segfault: session token invalidated after password reset.", {"article_id": "KB-1001", "title": "Auth service 401", "product_area": "auth", "tags": ["auth", "token"]}),
        ("billing charge twice same month", "Billing: idempotency key collision on subscription update.", {"article_id": "KB-1011", "title": "Duplicate billing charge", "product_area": "billing", "tags": ["billing", "payment"]}),
        ("server crashes with segfault at startup", "Crash: missing shared library causes SIGSEGV at startup.", {"article_id": "KB-1021", "title": "Application segfault startup", "product_area": "crash", "tags": ["crash", "segfault"]}),
        ("mobile app crashes on back button from payment", "Android: null pointer in payment fragment detach.", {"article_id": "KB-1033", "title": "Android back button crash", "product_area": "mobile", "tags": ["mobile", "android"]}),
        ("DNS resolution failure connection errors", "Network: secondary DNS resolver not configured.", {"article_id": "KB-1046", "title": "DNS resolution failure", "product_area": "network", "tags": ["network", "dns"]}),
    ]
    for user, assistant, metadata in articles:
        r.add_dialogue(user=user, assistant=assistant, metadata=metadata)
    r.finalize()
    return r


@pytest.fixture
def mock_llm():
    """Mock LLM that returns valid JSON patches."""
    from loops.llm import MockProvider
    return MockProvider(response='{"top_k": 7, "bm25_weight": 1.2}')


@pytest.fixture
def sample_dev_set(tmp_data):
    """Minimal dev_set.json with 5 pairs."""
    pairs = [
        {"ticket_id": f"T-{i:04d}", "ticket_text": text, "ground_truth_kb_id": kb_id, "product_area": pa, "csat_score": 5}
        for i, (text, kb_id, pa) in enumerate([
            ("app crash on login", "KB-1001", "auth"),
            ("billing charged twice", "KB-1011", "billing"),
            ("server segfault at startup", "KB-1021", "crash"),
            ("android back button crash", "KB-1033", "mobile"),
            ("dns lookup failure", "KB-1046", "network"),
        ])
    ]
    path = tmp_data / "dev_set.json"
    path.write_text(json.dumps(pairs))
    return path


@pytest.fixture
def failure_logger(tmp_data):
    from loops.failure_logger import FailureLogger
    return FailureLogger(tmp_data / "failure_log.jsonl")
