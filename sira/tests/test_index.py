import json
import tempfile
from pathlib import Path

import pytest

from src.index import CorpusIndex, build_and_save, tokenize
from tests.conftest import CORPUS_PATH


@pytest.fixture(scope="module")
def loaded_index():
    idx = CorpusIndex()
    idx.load_corpus(CORPUS_PATH)
    return idx


def test_load_corpus_count(loaded_index):
    assert len(loaded_index.articles) == 15


def test_load_corpus_no_empty_docs(loaded_index):
    for art in loaded_index.articles:
        assert art.get("body", "").strip(), f"{art['article_id']} has empty body"


def test_load_corpus_raises_on_empty_file():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w") as f:
        f.write("")
        f.flush()
        idx = CorpusIndex()
        with pytest.raises(ValueError, match="No articles found"):
            idx.load_corpus(f.name)


def test_load_corpus_raises_on_empty_body():
    with tempfile.NamedTemporaryFile(suffix=".jsonl", mode="w", delete=False) as f:
        json.dump({"article_id": "KB-BAD", "title": "T", "body": "   "}, f)
        name = f.name
    idx = CorpusIndex()
    with pytest.raises(ValueError, match="Empty body"):
        idx.load_corpus(name)
    Path(name).unlink()


def test_tokenizer_lowercase():
    tokens = tokenize("Authentication SERVICE Failed")
    assert all(t == t.lower() for t in tokens)
    assert "authentication" in tokens
    assert "service" in tokens
    assert "failed" in tokens


def test_tokenizer_min_length():
    tokens = tokenize("I am at it")
    assert all(len(t) >= 2 for t in tokens)
    assert "i" not in tokens
    assert "am" in tokens


def test_tokenizer_punctuation_stripped():
    tokens = tokenize("error: 503, timeout. re-try!")
    assert "." not in tokens
    assert "," not in tokens
    assert ":" not in tokens
    assert "!" not in tokens


def test_df_counter_populated(loaded_index):
    assert loaded_index.df_counter["authentication"] > 0


def test_df_counter_all_terms_present(loaded_index):
    for doc_tokens in loaded_index.tokenized:
        for term in set(doc_tokens):
            assert loaded_index.df_counter[term] > 0, f"Term '{term}' missing from df_counter"


def test_index_save_and_load(loaded_index, tmp_path):
    path = tmp_path / "test_index.pkl"
    loaded_index.save(path)
    restored = CorpusIndex.load(path)
    assert len(restored.articles) == len(loaded_index.articles)
    assert restored.df_counter["authentication"] == loaded_index.df_counter["authentication"]


def test_load_enriched_corpus_uses_enriched_body(tmp_path):
    article = {
        "article_id": "KB-ENR",
        "title": "Auth 503",
        "body": "Auth service 503.",
        "enriched_body": "Auth service 503. app wont open keeps crashing",
    }
    corpus_path = tmp_path / "enriched.jsonl"
    with open(corpus_path, "w") as f:
        f.write(json.dumps(article) + "\n")

    idx = CorpusIndex()
    idx.load_corpus(corpus_path)
    assert "app" in idx.df_counter
    assert "wont" in idx.df_counter
    assert "open" in idx.df_counter


def test_df_store_written(tmp_path):
    article = {"article_id": "KB-001", "title": "T", "body": "Body text."}
    corpus_path = tmp_path / "corpus.jsonl"
    with open(corpus_path, "w") as f:
        f.write(json.dumps(article) + "\n")

    index_path = tmp_path / "index.pkl"
    df_store_path = tmp_path / "df_store.json"
    build_and_save(corpus_path, index_path, df_store_path)

    assert df_store_path.exists()
    with open(df_store_path) as f:
        store = json.load(f)
    assert "body" in store


def test_df_store_contains_enriched_terms(tmp_path):
    article = {
        "article_id": "KB-ENR",
        "title": "Auth 503",
        "body": "Auth service 503.",
        "enriched_body": "Auth service 503. app wont open keeps crashing",
    }
    corpus_path = tmp_path / "corpus.jsonl"
    with open(corpus_path, "w") as f:
        f.write(json.dumps(article) + "\n")

    index_path = tmp_path / "index.pkl"
    df_store_path = tmp_path / "df_store.json"
    build_and_save(corpus_path, index_path, df_store_path)

    with open(df_store_path) as f:
        store = json.load(f)
    assert store.get("app", 0) > 0
    assert store.get("wont", 0) > 0
    assert store.get("open", 0) > 0
