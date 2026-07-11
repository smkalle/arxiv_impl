"""Iteration 3 — local backend tests."""
import numpy as np
import pytest


@pytest.fixture(scope="module")
def local_backend():
    from app.backends.local import LocalBackend
    return LocalBackend(model_id="all-MiniLM-L6-v2")


def test_local_embed_shape(local_backend):
    result = local_backend.embed(["hello world"])
    assert result.shape == (1, 384)


def test_local_embed_dtype(local_backend):
    result = local_backend.embed(["test"])
    assert result.dtype == np.float32


def test_local_embed_normalized(local_backend):
    result = local_backend.embed(["normalize this"])
    norm = np.linalg.norm(result[0])
    assert abs(norm - 1.0) < 1e-4


def test_local_embed_batch(local_backend):
    result = local_backend.embed(["first", "second", "third"])
    assert result.shape == (3, 384)


def test_local_cosine_similar(local_backend):
    """Semantically similar texts should have higher cosine similarity."""
    v1 = local_backend.embed(["onboarding new employee guide"])
    v2 = local_backend.embed(["welcome new team member onboarding"])
    v3 = local_backend.embed(["kafka event streaming pipeline"])
    sim_12 = float(np.dot(v1[0], v2[0]))
    sim_13 = float(np.dot(v1[0], v3[0]))
    assert sim_12 > sim_13, f"Expected similar > dissimilar, got {sim_12:.3f} <= {sim_13:.3f}"


def test_local_embed_query(local_backend):
    vec = local_backend.embed_query("test query")
    assert vec.shape == (384,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-4


def test_local_backend_name(local_backend):
    assert local_backend.name == "local"


def test_local_backend_dim(local_backend):
    assert local_backend.embed_dim == 384


def test_factory_local(monkeypatch):
    import os
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL_ID", "all-MiniLM-L6-v2")
    monkeypatch.setenv("EMBED_DIM", "384")
    from app.config import reset_settings
    reset_settings()
    from app.backends.factory import get_backend
    b = get_backend()
    assert b.name == "local"
