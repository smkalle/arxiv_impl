"""Tests for SimpleMem stub."""
import pytest
from simplemem_router_stub import StubSimpleMemRouter


def test_create_returns_self():
    r = StubSimpleMemRouter()
    assert r.create("text") is r


def test_ask_returns_results(stub_router):
    results = stub_router.ask("app crash on login", config=None)
    assert isinstance(results, list)
    assert len(results) > 0
    assert "article_id" in results[0]


def test_ask_top_k_respected(stub_router):
    from loops.action_space import RetrievalConfig
    config = RetrievalConfig(top_k=2)
    results = stub_router.ask("crash", config=config)
    assert len(results) <= 2


def test_empty_corpus_returns_empty():
    r = StubSimpleMemRouter().create("text")
    r.finalize()
    assert r.ask("anything") == []


def test_entity_swap_extra_accepted(stub_router):
    from loops.action_space import RetrievalConfig
    config = RetrievalConfig().apply_patch({
        "entity_swap": True,
        "entity_swap_domain": "it_support",
    })
    results = stub_router.ask("login crash", config=config)
    assert isinstance(results, list)


def test_article_id_in_results(stub_router):
    results = stub_router.ask("billing charge twice", config=None)
    ids = [r["article_id"] for r in results]
    assert "KB-1011" in ids
