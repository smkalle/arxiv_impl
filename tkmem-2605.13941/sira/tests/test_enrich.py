from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

from src.enrich import _parse_terms, enrich_article, enrich_file, normalize_host


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def test_normalize_host_accepts_bare_ollama_host() -> None:
    assert normalize_host("127.0.0.1:11434") == "http://127.0.0.1:11434"
    assert normalize_host("http://localhost:11434") == "http://localhost:11434"


def test_parse_terms_accepts_lists_and_filters_invalid_terms() -> None:
    raw = """
    - frozen screen
    - login
    - ABC123
    - concatenationguard
    - frozen screen
    - can't get in
    """
    original = "Login troubleshooting article for authentication failures."

    terms = _parse_terms(raw, original)

    assert terms == ["frozen screen", "can't get in"]


def test_parse_terms_accepts_json_array() -> None:
    raw = '["keeps closing", "can not pay", "email never came"]'

    assert _parse_terms(raw, "unrelated article body") == [
        "keeps closing",
        "can not pay",
        "email never came",
    ]


def test_enrich_article_adds_schema_fields_with_mocked_ollama() -> None:
    article = {
        "id": "KB-1",
        "title": "Billing renewal failed",
        "body": "Payment processor rejected the saved card.",
        "last_updated": "2026-05-01T00:00:00Z",
    }

    with patch("src.enrich.call_ollama", return_value="- charged again\n- card won't work"):
        enriched, changed, used_fallback = enrich_article(
            article,
            host="http://ollama.test",
            model="qwen2.5:14b",
            temperature=0.3,
        )

    assert changed is True
    assert used_fallback is False
    assert enriched["id"] == "KB-1"
    assert enriched["enriched_terms"] == ["charged again", "card won't work"]
    assert "Customer language: charged again; card won't work" in enriched["enriched_body"]
    assert enriched["enriched_at"].endswith("Z")
    assert enriched["last_updated"] == "2026-05-01T00:00:00Z"
    assert enriched["enrichment_backend"] == "ollama"


def test_enrich_article_skips_current_enrichment() -> None:
    article = {
        "id": "KB-1",
        "title": "Already enriched",
        "body": "Body",
        "last_updated": "2026-05-01T00:00:00Z",
        "enriched_at": "2026-05-02T00:00:00Z",
        "enriched_terms": ["existing"],
    }

    with patch("src.enrich.call_ollama") as call_ollama:
        enriched, changed, used_fallback = enrich_article(
            article,
            host="http://ollama.test",
            model="qwen2.5:14b",
            temperature=0.3,
        )

    call_ollama.assert_not_called()
    assert changed is False
    assert used_fallback is False
    assert enriched == article


def test_enrich_file_counts_enriched_skipped_and_failed(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        "\n".join(
            [
                json.dumps({"id": "KB-1", "title": "One", "body": "First body"}),
                json.dumps(
                    {
                        "id": "KB-2",
                        "title": "Two",
                        "body": "Second body",
                        "last_updated": "2026-05-01T00:00:00Z",
                        "enriched_at": "2026-05-02T00:00:00Z",
                    }
                ),
                json.dumps({"id": "KB-3", "title": "Three", "body": "Third body"}),
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    def fake_call(article, host, model, temperature):
        if article["id"] == "KB-3":
            raise requests.RequestException("backend down")
        return "- user wording\n- help needed"

    with patch("src.enrich.call_ollama", side_effect=fake_call):
        stats = enrich_file(
            input_path,
            output_path,
            host="http://ollama.test",
            model="qwen2.5:14b",
            allow_fallback=False,
        )

    articles = read_jsonl(output_path)
    assert stats.processed == 3
    assert stats.enriched == 1
    assert stats.skipped == 1
    assert stats.failed == 1
    assert articles[0]["enriched_terms"] == ["user wording", "help needed"]
    assert "enriched_terms" not in articles[2]


def test_enrich_file_uses_fallback_when_backend_unreachable(tmp_path: Path) -> None:
    input_path = tmp_path / "input.jsonl"
    output_path = tmp_path / "output.jsonl"
    input_path.write_text(
        '{"id":"KB-1","title":"Login crash","body":"App closes during sign in."}\n',
        encoding="utf-8",
    )

    with patch("src.enrich.call_ollama", side_effect=requests.RequestException("down")):
        stats = enrich_file(input_path, output_path, allow_fallback=True)

    articles = read_jsonl(output_path)
    assert stats.enriched == 1
    assert stats.failed == 0
    assert articles[0]["enrichment_backend"] == "heuristic-fallback"
    assert articles[0]["enriched_terms"]
