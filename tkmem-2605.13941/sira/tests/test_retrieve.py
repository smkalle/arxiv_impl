from __future__ import annotations

import pytest

from src.index import CorpusIndex
from src.retrieve import _set_index, load_index, retrieve


def test_retrieve_requires_loaded_index() -> None:
    with pytest.raises(RuntimeError, match="index is not loaded"):
        retrieve("app crash")


def test_plain_retrieve_ranks_relevant_article_first(tiny_corpus) -> None:
    index = CorpusIndex.from_jsonl(tiny_corpus)
    _set_index(index)

    results = retrieve("app keeps crashing after login", top_k=2)

    assert results[0]["id"] == "KB-A"
    assert results[0]["rank"] == 1
    assert results[0]["score"] >= results[1]["score"]
    assert "session token" in results[0]["snippet"]


def test_load_index_restores_pickled_index(tmp_path, tiny_corpus) -> None:
    index = CorpusIndex.from_jsonl(tiny_corpus)
    output_path = tmp_path / "index.pkl"

    import pickle

    with output_path.open("wb") as handle:
        pickle.dump(index, handle)

    loaded = load_index(output_path)
    results = retrieve("password email spam", top_k=1)

    assert loaded.size == 3
    assert results[0]["id"] == "KB-C"
