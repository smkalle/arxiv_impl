from __future__ import annotations

import json

import pytest

from src.index import CorpusIndex, build_and_save, load_saved_index, tokenize


def test_tokenize_lowercases_filters_short_and_symbol_tokens() -> None:
    assert tokenize("A B2 APP, crashed! -- ? x") == ["b2", "app", "crashed"]


def test_corpus_index_loads_articles_and_counts_document_frequency(tiny_corpus) -> None:
    index = CorpusIndex.from_jsonl(tiny_corpus)

    assert index.size == 3
    assert index.articles[0]["id"] == "KB-A"
    assert index.df_counter["login"] == 1
    assert index.df_counter["renewal"] == 1


def test_build_and_save_writes_pickle_and_df_store(tmp_path, tiny_corpus) -> None:
    output_path = tmp_path / "bm25_index.pkl"

    built = build_and_save(tiny_corpus, output_path)
    loaded = load_saved_index(output_path)
    df_store = json.loads((tmp_path / "df_store.json").read_text(encoding="utf-8"))

    assert output_path.exists()
    assert loaded.size == built.size
    assert df_store["login"] == 1
    assert df_store["password"] == 1


def test_jsonl_validation_requires_core_fields(tmp_path) -> None:
    corpus_path = tmp_path / "bad.jsonl"
    corpus_path.write_text('{"id":"KB-1","title":"Missing body"}\n', encoding="utf-8")

    with pytest.raises(ValueError, match="missing required field"):
        CorpusIndex.from_jsonl(corpus_path)
