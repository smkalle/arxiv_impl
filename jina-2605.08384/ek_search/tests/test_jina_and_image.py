"""Iteration 5 — Jina API backend mock tests and backend switching."""
import json
import numpy as np
import pytest
from unittest.mock import patch, MagicMock


def make_jina_response(n: int, dim: int = 512) -> dict:
    """Fake Jina API response payload."""
    rng = np.random.default_rng(42)
    return {
        "data": [
            {"embedding": rng.random(dim).tolist(), "index": i}
            for i in range(n)
        ],
        "model": "jina-embeddings-v5-omni-small",
        "usage": {"prompt_tokens": 10, "total_tokens": 10},
    }


@pytest.fixture
def jina_backend():
    from app.backends.jina_api import JinaAPIBackend
    return JinaAPIBackend(api_key="test_key", dimensions=512)


def test_jina_backend_name(jina_backend):
    assert jina_backend.name == "jina_api"


def test_jina_backend_dim(jina_backend):
    assert jina_backend.embed_dim == 512


def test_jina_embed_calls_api(jina_backend):
    mock_response = MagicMock()
    mock_response.json.return_value = make_jina_response(2, dim=512)
    mock_response.raise_for_status = MagicMock()

    with patch("app.backends.jina_api.httpx.post", return_value=mock_response) as mock_post:
        result = jina_backend.embed(["hello", "world"])

    assert result.shape == (2, 512)
    assert result.dtype == np.float32
    mock_post.assert_called_once()


def test_jina_request_payload(jina_backend):
    mock_response = MagicMock()
    mock_response.json.return_value = make_jina_response(1)
    mock_response.raise_for_status = MagicMock()

    with patch("app.backends.jina_api.httpx.post", return_value=mock_response) as mock_post:
        jina_backend.embed(["test input"])

    call_kwargs = mock_post.call_args
    payload = call_kwargs.kwargs.get("json") or call_kwargs.args[1]
    assert payload["model"] == "jina-embeddings-v5-omni-small"
    assert payload["dimensions"] == 512
    assert len(payload["input"]) == 1
    assert payload["input"][0]["text"] == "test input"


def test_jina_auth_header(jina_backend):
    mock_response = MagicMock()
    mock_response.json.return_value = make_jina_response(1)
    mock_response.raise_for_status = MagicMock()

    with patch("app.backends.jina_api.httpx.post", return_value=mock_response) as mock_post:
        jina_backend.embed(["auth test"])

    headers = mock_post.call_args.kwargs.get("headers") or mock_post.call_args.args[2]
    assert "Authorization" in headers
    assert headers["Authorization"] == "Bearer test_key"


def test_jina_normalized_output(jina_backend):
    mock_response = MagicMock()
    mock_response.json.return_value = make_jina_response(3)
    mock_response.raise_for_status = MagicMock()

    with patch("app.backends.jina_api.httpx.post", return_value=mock_response):
        result = jina_backend.embed(["a", "b", "c"])

    for i in range(3):
        norm = np.linalg.norm(result[i])
        assert abs(norm - 1.0) < 1e-4


def test_backend_switch_to_jina(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "jina_api")
    monkeypatch.setenv("JINA_API_KEY", "fake_key")
    from app.config import reset_settings
    reset_settings()
    from app.backends.factory import get_backend
    b = get_backend()
    assert b.name == "jina_api"


def test_backend_switch_stub_to_local(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    monkeypatch.setenv("LOCAL_MODEL_ID", "all-MiniLM-L6-v2")
    from app.config import reset_settings
    reset_settings()
    from app.backends.factory import get_backend
    b = get_backend()
    assert b.name == "local"


def test_image_ingest_and_search(tmp_path):
    """Image files ingested with modality=image, queryable."""
    import os
    from PIL import Image as PILImage
    os.environ["EMBEDDING_BACKEND"] = "stub"
    os.environ["EMBED_DIM"] = "64"
    os.environ["CHROMA_PATH"] = str(tmp_path / "chroma")
    os.environ["CHROMA_COLLECTION"] = "img-test"

    from app.config import reset_settings
    reset_settings()
    from app.api import app, reset_singletons
    reset_singletons()

    # Create sample image
    img_dir = tmp_path / "images"
    img_dir.mkdir()
    img = PILImage.new("RGB", (50, 50), color=(100, 150, 200))
    img.save(img_dir / "logo.png")

    from fastapi.testclient import TestClient
    with TestClient(app) as c:
        r = c.post("/ingest", json={"source": "filesystem", "path": str(img_dir)})
        assert r.json()["ingested"] >= 1

        stats = c.get("/stats").json()
        assert "image" in stats["by_modality"]

        r2 = c.post("/search", json={"query_text": "logo image", "n_results": 5})
        results = r2.json()["results"]
        assert len(results) >= 1
