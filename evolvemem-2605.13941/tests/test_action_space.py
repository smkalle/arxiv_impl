"""Tests for RetrievalConfig open-schema."""
import pytest
from loops.action_space import RetrievalConfig


def test_known_field_patch():
    cfg = RetrievalConfig()
    new = cfg.apply_patch({"top_k": 10})
    assert new.top_k == 10
    assert cfg.top_k == 5  # original unchanged


def test_unknown_key_goes_to_extras():
    cfg = RetrievalConfig()
    new = cfg.apply_patch({"entity_swap": True, "entity_swap_domain": "it_support"})
    assert new._extras["entity_swap"] is True
    assert new._extras["entity_swap_domain"] == "it_support"


def test_roundtrip_to_from_dict():
    cfg = RetrievalConfig(top_k=8).apply_patch({"recency_weight": 0.15})
    d = cfg.to_dict()
    assert d["top_k"] == 8
    assert d["recency_weight"] == 0.15
    restored = RetrievalConfig.from_dict(d)
    assert restored.top_k == 8
    assert restored._extras["recency_weight"] == 0.15


def test_meta_keys_ignored():
    cfg = RetrievalConfig()
    new = cfg.apply_patch({"__round": 3, "__rationale": "test"})
    assert "__round" not in new._extras
    assert "__rationale" not in new._extras


def test_discovered_dimensions():
    cfg = RetrievalConfig()
    new = cfg.apply_patch({"new_dim_1": "val", "new_dim_2": 42})
    dims = new.discovered_dimensions()
    assert "new_dim_1" in dims
    assert "new_dim_2" in dims


def test_bool_coercion():
    cfg = RetrievalConfig()
    new = cfg.apply_patch({"rerank": "true"})
    assert new.rerank is True


def test_float_coercion():
    cfg = RetrievalConfig()
    new = cfg.apply_patch({"bm25_weight": "1.5"})
    assert new.bm25_weight == pytest.approx(1.5)
