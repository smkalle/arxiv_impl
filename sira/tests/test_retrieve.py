import pytest
from collections import Counter
from pathlib import Path
from unittest.mock import MagicMock, patch

from rank_bm25 import BM25Okapi

import src.retrieve as retrieve_module
from src.index import CorpusIndex, tokenize
from src.retrieve import IndexNotLoadedError, _set_index, retrieve, sira_retrieve
from tests.conftest import CORPUS_PATH


@pytest.fixture(autouse=True)
def reset_index():
    _set_index(None)
    yield
    _set_index(None)


@pytest.fixture
def loaded_index():
    idx = CorpusIndex()
    idx.load_corpus(CORPUS_PATH)
    _set_index(idx)
    return idx


@pytest.fixture
def enriched_index():
    _set_index(None)
    articles = [
        {
            "article_id": "KB-001",
            "title": "Authentication service 503",
            "body": "Auth service 503.",
            "enriched_body": "Authentication service 503. app wont open keeps crashing login loop",
            "enriched_terms": ["app wont open", "keeps crashing", "login loop"],
        },
        {
            "article_id": "KB-002",
            "title": "Billing issue",
            "body": "Billing problem.",
            "enriched_body": "Billing problem. charged twice refund missing",
            "enriched_terms": ["charged twice", "refund missing"],
        },
        {
            "article_id": "KB-003",
            "title": "Password reset email",
            "body": "Password reset.",
            "enriched_body": "Password reset email sendgrid spam delivery",
            "enriched_terms": ["email not arriving", "junk folder"],
        },
        {
            "article_id": "KB-004",
            "title": "Mobile app crash",
            "body": "Mobile crash.",
            "enriched_body": "Mobile app crash startup ios android",
            "enriched_terms": ["phone frozen", "app wont start"],
        },
        {
            "article_id": "KB-005",
            "title": "Two factor authentication",
            "body": "2FA setup.",
            "enriched_body": "Two factor authentication totp recovery backup codes",
            "enriched_terms": ["authenticator app", "backup codes"],
        },
    ]
    # Pad with dummy articles so N >= 100, making tau=0.01 allow df=1 terms
    for i in range(6, 101):
        articles.append({
            "article_id": f"KB-{i:03d}",
            "title": f"Dummy article {i}",
            "body": "Placeholder content.",
            "enriched_body": "Placeholder content.",
            "enriched_terms": [],
        })

    idx = CorpusIndex()
    idx.articles = articles
    idx.tokenized = [
        tokenize(a["title"] + " " + a["enriched_body"]) for a in articles
    ]
    idx.bm25 = BM25Okapi(idx.tokenized)
    idx.df_counter = Counter()
    for doc_tokens in idx.tokenized:
        for t in set(doc_tokens):
            idx.df_counter[t] += 1
    for art in articles:
        for term in art.get("enriched_terms", []):
            idx.df_counter[term.lower()] += 1
    _set_index(idx)
    yield idx
    _set_index(None)


# ---------------------------------------------------------------------------
# Plain BM25 tests (Iteration 1)
# ---------------------------------------------------------------------------

def test_retrieve_authentication_503_in_top3(loaded_index):
    results = retrieve("authentication 503", top_k=5)
    top3_ids = [r["article_id"] for r in results[:3]]
    assert "KB-001" in top3_ids, f"KB-001 not in top 3: {top3_ids}"


def test_retrieve_returns_correct_fields(loaded_index):
    results = retrieve("mobile app crash", top_k=3)
    assert results
    for r in results:
        assert "article_id" in r
        assert "title" in r
        assert "score" in r
        assert "snippet" in r


def test_retrieve_scores_descending(loaded_index):
    results = retrieve("authentication login", top_k=5)
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


def test_retrieve_respects_top_k(loaded_index):
    results = retrieve("authentication", top_k=3)
    assert len(results) <= 3


def test_retrieve_without_index_raises():
    with pytest.raises(IndexNotLoadedError):
        retrieve("any query")


def test_retrieve_empty_corpus_raises():
    empty_idx = CorpusIndex()
    _set_index(empty_idx)
    with pytest.raises(IndexNotLoadedError):
        retrieve("any query")


def test_retrieve_unknown_query_returns_empty(loaded_index):
    results = retrieve("xyzzy quux frobnicate zzz123")
    assert results == [], f"Expected empty list, got {results}"


def test_retrieve_snippet_length(loaded_index):
    results = retrieve("billing subscription", top_k=5)
    for r in results:
        assert len(r["snippet"]) <= 203, "Snippet should be truncated to ~200 chars + ellipsis"


# ---------------------------------------------------------------------------
# SIRA tests (Iteration 3)
# ---------------------------------------------------------------------------

def test_sira_score_gte_plain_bm25(enriched_index):
    with patch("src.retrieve.generate_sketch", return_value=["keeps crashing"]):
        sira_response = sira_retrieve("authentication service", top_k=1)
    plain_results = retrieve("authentication service", top_k=1)

    assert plain_results
    top_plain = plain_results[0]
    sira_results = sira_response["results"]
    assert sira_results
    top_sira = sira_results[0]

    # same article should be top
    assert top_sira["article_id"] == top_plain["article_id"]
    # with sketch weight the score must be >= plain score
    assert top_sira["score"] >= top_plain["score"]


def test_sira_fallback_on_timeout(enriched_index):
    with patch("src.retrieve.generate_sketch", side_effect=TimeoutError("mock timeout")):
        response = sira_retrieve("authentication service", top_k=1)

    assert response["fallback_used"] is True
    assert response["results"]  # should still return plain BM25 results


def test_sira_audit_fields_present(enriched_index):
    with patch("src.retrieve.generate_sketch", return_value=["keeps crashing"]):
        response = sira_retrieve("authentication service", top_k=1)

    assert "results" in response
    assert "sketch_terms_generated" in response
    assert "sketch_terms_validated" in response
    assert "sketch_terms_rejected" in response
    assert "fallback_used" in response
    assert "latency_ms" in response
    assert "hallucination_rate" in response


def test_sira_hallucination_rate_accuracy(enriched_index):
    # "keeps crashing" is in corpus, "fake_term" is not
    with patch("src.retrieve.generate_sketch", return_value=["keeps crashing", "fake_term"]):
        response = sira_retrieve("authentication service", top_k=1)

    assert response["sketch_terms_generated"] == ["keeps crashing", "fake_term"]
    assert response["sketch_terms_validated"] == ["keeps crashing"]
    assert response["sketch_terms_rejected"] == ["fake_term"]
    assert response["hallucination_rate"] == 0.5


def test_matched_original_terms(enriched_index):
    with patch("src.retrieve.generate_sketch", return_value=[]):
        response = sira_retrieve("authentication service", top_k=1)

    top = response["results"][0]
    assert "authentication" in top["matched_original_terms"] or "service" in top["matched_original_terms"]


def test_matched_enriched_terms_from_query_and_sketch(enriched_index):
    # query contains "app wont open" which is an enriched term
    # sketch contains "login loop" which is also an enriched term
    with patch("src.retrieve.generate_sketch", return_value=["login loop"]):
        response = sira_retrieve("app wont open", top_k=1)

    top = response["results"][0]
    matched = top["matched_enriched_terms"]
    assert "app wont open" in matched
    assert "login loop" in matched
