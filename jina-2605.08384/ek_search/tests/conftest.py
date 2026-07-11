"""pytest configuration and shared fixtures."""
import os
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure project root is on path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Force stub backend for all tests by default
os.environ.setdefault("EMBEDDING_BACKEND", "stub")
os.environ.setdefault("EMBED_DIM", "64")   # small dim for fast tests


@pytest.fixture(autouse=True)
def reset_app_singletons():
    """Reset all module-level singletons before each test."""
    from app import config as cfg
    cfg.reset_settings()
    try:
        from app import api
        api.reset_singletons()
    except Exception:
        pass
    yield
    cfg.reset_settings()


@pytest.fixture
def tmp_chroma(tmp_path):
    """Temporary Chroma store — isolated per test."""
    from app.config import override_settings, Settings
    override_settings(Settings(
        embedding_backend="stub",
        embed_dim=64,
        chroma_path=str(tmp_path / "chroma"),
        chroma_collection="test-collection",
    ))
    from app.vector_store import ChromaVectorStore
    store = ChromaVectorStore(
        path=str(tmp_path / "chroma"),
        collection_name="test-collection",
    )
    yield store


@pytest.fixture
def stub_backend():
    from app.backends.stub import StubBackend
    return StubBackend(embed_dim=64)


@pytest.fixture
def sample_docs():
    from app.models import Document
    return [
        Document(id="src:test:doc1", content="onboarding guide for new employees", modality="text", source_system="test", asset_url="/doc1"),
        Document(id="src:test:doc2", content="kubernetes deployment runbook rollback", modality="text", source_system="test", asset_url="/doc2"),
        Document(id="src:test:doc3", content="security policy access control vault", modality="text", source_system="test", asset_url="/doc3"),
    ]
