"""Iteration 0 — config tests."""
import os
import pytest
from app.config import Settings, get_settings, override_settings, reset_settings


def test_defaults():
    s = Settings()
    assert s.embedding_backend == "stub"
    assert s.embed_dim == 384
    assert s.chroma_collection == "multimodal-knowledge"


def test_from_env(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "local")
    monkeypatch.setenv("EMBED_DIM", "128")
    monkeypatch.setenv("LOCAL_MODEL_ID", "all-MiniLM-L6-v2")
    reset_settings()
    s = Settings.from_env()
    assert s.embedding_backend == "local"
    assert s.embed_dim == 128
    assert s.local_model_id == "all-MiniLM-L6-v2"


def test_override():
    custom = Settings(embedding_backend="stub", embed_dim=32)
    override_settings(custom)
    s = get_settings()
    assert s.embed_dim == 32
    assert s.embedding_backend == "stub"


def test_reset(monkeypatch):
    monkeypatch.setenv("EMBEDDING_BACKEND", "stub")
    monkeypatch.setenv("EMBED_DIM", "64")
    reset_settings()
    s = get_settings()
    assert s.embedding_backend == "stub"
    assert s.embed_dim == 64


def test_invalid_port_fallback():
    # Ensure type coercion works
    s = Settings(api_port=9999)
    assert isinstance(s.api_port, int)
