import json
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.enrich import _parse_terms, enrich_article, enrich_corpus


def test_parse_terms_filters_terms_in_original_text():
    raw = "app crash, login error, authentication service"
    original = "The authentication service may return HTTP 503 errors"
    terms = _parse_terms(raw, original)
    assert "authentication service" not in terms
    assert "app crash" in terms
    assert "login error" in terms


def test_enrich_article_produces_required_fields(monkeypatch):
    mock_llm = MagicMock(return_value="app wont open, keeps crashing, login loop")
    article = {
        "article_id": "KB-TEST",
        "title": "Authentication service 503",
        "body": "The authentication service may return HTTP 503 errors.",
    }
    result = enrich_article(article, llm_call=mock_llm, model="test-model")

    assert result["article_id"] == "KB-TEST"
    assert result["title"] == "Authentication service 503"
    assert result["original_body"] == article["body"]
    assert "enriched_body" in result
    assert result["enriched_terms"] == ["app wont open", "keeps crashing", "login loop"]
    assert result["model_used"] == "test-model"
    assert "enriched_at" in result


def test_enrich_article_retries_then_raises(monkeypatch):
    mock_llm = MagicMock(side_effect=RuntimeError("LLM down"))
    article = {
        "article_id": "KB-TEST",
        "title": "T",
        "body": "Body text.",
    }
    with pytest.raises(RuntimeError, match="LLM down"):
        enrich_article(article, llm_call=mock_llm, model="test-model", max_retries=2)
    assert mock_llm.call_count == 2


def test_enrich_corpus_idempotency_skips_current():
    now = datetime.now(timezone.utc).isoformat()
    articles = [
        {
            "article_id": "KB-001",
            "title": "Auth 503",
            "body": "Auth service 503.",
            "last_updated": "2026-01-01T00:00:00+00:00",
            "enriched_at": now,
            "enriched_terms": ["old term"],
        }
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for art in articles:
            f.write(json.dumps(art) + "\n")
        input_path = f.name

    output_path = tempfile.mktemp(suffix=".jsonl")
    mock_llm = MagicMock(return_value="new term")

    stats = enrich_corpus(input_path, output_path, llm_call=mock_llm)

    assert stats["skipped"] == 1
    assert stats["enriched"] == 0
    assert stats["failed"] == 0
    assert mock_llm.call_count == 0

    with open(output_path) as f:
        out = json.loads(f.readline())
    assert out["enriched_terms"] == ["old term"]

    Path(input_path).unlink(missing_ok=True)
    Path(output_path).unlink(missing_ok=True)


def test_enrich_corpus_llm_failure_logs_and_skips():
    articles = [
        {"article_id": "KB-001", "title": "Auth 503", "body": "Auth service 503."},
        {"article_id": "KB-002", "title": "Billing", "body": "Billing issue."},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for art in articles:
            f.write(json.dumps(art) + "\n")
        input_path = f.name

    output_path = tempfile.mktemp(suffix=".jsonl")
    mock_llm = MagicMock(side_effect=[RuntimeError("fail"), "app crash"])

    stats = enrich_corpus(input_path, output_path, llm_call=mock_llm, max_retries=1)

    assert stats["failed"] == 1
    assert stats["enriched"] == 1

    with open(output_path) as f:
        lines = f.readlines()
    assert len(lines) == 2

    Path(input_path).unlink(missing_ok=True)
    Path(output_path).unlink(missing_ok=True)


def test_enrich_corpus_output_has_enriched_body():
    articles = [
        {"article_id": "KB-001", "title": "Auth 503", "body": "Auth service 503."},
    ]
    with tempfile.NamedTemporaryFile(mode="w", suffix=".jsonl", delete=False) as f:
        for art in articles:
            f.write(json.dumps(art) + "\n")
        input_path = f.name

    output_path = tempfile.mktemp(suffix=".jsonl")
    mock_llm = MagicMock(return_value="app wont open, keeps crashing")

    enrich_corpus(input_path, output_path, llm_call=mock_llm)

    with open(output_path) as f:
        out = json.loads(f.readline())

    assert "enriched_body" in out
    assert "app wont open" in out["enriched_body"]
    assert out["original_body"] == "Auth service 503."

    Path(input_path).unlink(missing_ok=True)
    Path(output_path).unlink(missing_ok=True)
