"""Iteration 0 — stub backend tests."""
import numpy as np
import pytest
from app.backends.stub import StubBackend


@pytest.fixture
def backend():
    return StubBackend(embed_dim=64)


def test_embed_shape(backend):
    result = backend.embed(["hello world"])
    assert result.shape == (1, 64)


def test_embed_dtype(backend):
    result = backend.embed(["test"])
    assert result.dtype == np.float32


def test_embed_l2_norm(backend):
    result = backend.embed(["normalize me"])
    norm = np.linalg.norm(result[0])
    assert abs(norm - 1.0) < 1e-5


def test_embed_batch(backend):
    inputs = ["first", "second", "third"]
    result = backend.embed(inputs)
    assert result.shape == (3, 64)
    for i in range(3):
        assert abs(np.linalg.norm(result[i]) - 1.0) < 1e-5


def test_deterministic(backend):
    r1 = backend.embed(["same input"])
    r2 = backend.embed(["same input"])
    np.testing.assert_array_equal(r1, r2)


def test_different_inputs_differ(backend):
    r1 = backend.embed(["hello"])
    r2 = backend.embed(["world"])
    assert not np.allclose(r1, r2)


def test_embed_query(backend):
    vec = backend.embed_query("test query")
    assert vec.shape == (64,)
    assert abs(np.linalg.norm(vec) - 1.0) < 1e-5


def test_factory_stub():
    from app.config import Settings, override_settings
    from app.backends.factory import get_backend
    override_settings(Settings(embedding_backend="stub", embed_dim=32))
    b = get_backend()
    assert b.name == "stub"
    assert b.embed_dim == 32


def test_factory_unknown():
    from app.config import Settings, override_settings
    from app.backends.factory import get_backend
    override_settings(Settings(embedding_backend="unknown_xyz"))
    with pytest.raises(ValueError, match="Unknown EMBEDDING_BACKEND"):
        get_backend()
