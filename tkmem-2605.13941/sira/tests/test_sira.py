from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from src.df_filter import validate_sketch_terms
from src.index import CorpusIndex, build_and_save
from src.retrieve import _set_index, evolved_retrieve, sira_retrieve
from src.sketch import generate_sketch, parse_sketch_terms


def test_validate_sketch_terms_accepts_absent_over_threshold_and_duplicate() -> None:
    result = validate_sketch_terms(
        ["session", "token", "unknown", "common", "session"],
        {"session": 1, "token": 1, "common": 5},
        corpus_size=100,
        tau=0.01,
    )

    assert result["accepted"] == ["session", "token"]
    assert [item["reason"] for item in result["rejected"]] == [
        "absent_from_corpus",
        "df_over_threshold",
        "duplicate",
    ]
    assert result["hallucination_rate"] == pytest.approx(3 / 5)


def test_parse_sketch_terms_limits_to_twelve() -> None:
    raw = "\n".join(f"- term item{idx}" for idx in range(20))

    assert len(parse_sketch_terms(raw)) == 12


def test_generate_sketch_uses_heuristic_fallback() -> None:
    with patch("src.sketch.requests.post", side_effect=requests.RequestException("down")):
        terms = generate_sketch("app crash on login")

    assert "authentication" in terms
    assert "session" in terms


def test_evolved_retrieve_combines_plain_and_sketch_scores(tmp_path: Path, tiny_corpus) -> None:
    index_path = tmp_path / "idx.pkl"
    index = build_and_save(tiny_corpus, index_path)
    _set_index(index)
    df_path = tmp_path / "df_store.json"

    with patch("src.retrieve.generate_sketch", return_value=["login", "session", "token"]):
        payload = evolved_retrieve(
            "keeps crashing",
            top_k=2,
            tau=1.0,
            weight=2.0,
            df_store_path=df_path,
        )

    assert payload["fallback_used"] is False
    assert payload["results"][0]["id"] == "KB-A"
    assert payload["results"][0]["score"] > payload["results"][0]["plain_score"]
    assert payload["trace"]["accepted_terms"] == ["login", "session", "token"]


def test_evolved_retrieve_falls_back_when_no_terms_pass(tmp_path: Path, tiny_corpus) -> None:
    index = CorpusIndex.from_jsonl(tiny_corpus)
    _set_index(index)
    df_path = tmp_path / "df_store.json"
    df_path.write_text(json.dumps({"common": 3}), encoding="utf-8")

    with patch("src.retrieve.generate_sketch", return_value=["absent"]):
        payload = evolved_retrieve("password email", top_k=1, df_store_path=df_path)

    assert payload["fallback_used"] is True
    assert payload["results"][0]["id"] == "KB-C"


def test_sira_alias_remains_backward_compatible(tmp_path: Path, tiny_corpus) -> None:
    index = CorpusIndex.from_jsonl(tiny_corpus)
    _set_index(index)
    df_path = tmp_path / "df_store.json"
    df_path.write_text(json.dumps({"password": 1, "email": 1}), encoding="utf-8")

    with patch("src.retrieve.generate_sketch", return_value=["password", "email"]):
        payload = sira_retrieve("password email", top_k=1, df_store_path=df_path, tau=1.0)

    assert payload["results"][0]["id"] == "KB-C"
