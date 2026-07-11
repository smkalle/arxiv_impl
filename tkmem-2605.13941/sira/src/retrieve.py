"""Retrieval API for the arXiv 2605.13941/TKMEM implementation."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from src.df_filter import load_df_store, validate_sketch_terms
from src.index import CorpusIndex, load_saved_index, make_snippet, tokenize
from src.sketch import generate_sketch


_index: CorpusIndex | None = None


def load_index(index_path: str | Path = "data/bm25_index.pkl") -> CorpusIndex:
    global _index
    _index = load_saved_index(index_path)
    return _index


def _set_index(index: CorpusIndex | None) -> None:
    global _index
    _index = index


def retrieve(query: str, top_k: int = 5) -> list[dict[str, Any]]:
    if _index is None:
        raise RuntimeError("BM25 index is not loaded. Call load_index() first.")
    return _index.search(query, top_k=top_k)


def evolved_retrieve(
    query: str,
    top_k: int = 5,
    tau: float = 0.01,
    weight: float = 1.5,
    df_store_path: str | Path = "data/df_store.json",
) -> dict[str, Any]:
    if _index is None:
        raise RuntimeError("BM25 index is not loaded. Call load_index() first.")

    original_tokens = _index.search(query, top_k=_index.size)
    fallback_used = False
    try:
        generated_terms = generate_sketch(query)
        df_store = load_df_store(df_store_path)
        validation = validate_sketch_terms(generated_terms, df_store, _index.size, tau=tau)
        accepted_terms = validation["accepted"]
    except Exception as exc:  # Keep retrieval available if sketching fails.
        generated_terms = []
        validation = {"accepted": [], "rejected": [{"term": "", "reason": str(exc), "df": 0}], "hallucination_rate": 1.0}
        accepted_terms = []
        fallback_used = True

    if not accepted_terms:
        fallback_used = True
        return {
            "results": retrieve(query, top_k=top_k),
            "fallback_used": fallback_used,
            "trace": {
                "plain_tokens": query.split(),
                "generated_terms": generated_terms,
                "accepted_terms": accepted_terms,
                "rejected_terms": validation["rejected"],
                "hallucination_rate": validation["hallucination_rate"],
                "tau": tau,
                "weight": weight,
            },
        }

    orig_scores = _index.bm25.get_scores(tokenize(query))
    sketch_tokens: list[str] = []
    for term in accepted_terms:
        sketch_tokens.extend(tokenize(term))
    sketch_scores = _index.bm25.get_scores(sketch_tokens)
    combined = orig_scores + (weight * sketch_scores)
    ranked = sorted(range(len(combined)), key=lambda idx: combined[idx], reverse=True)
    results: list[dict[str, Any]] = []
    plain_by_id = {result["id"]: result["score"] for result in original_tokens}
    sketch_only = _index.search_tokens(sketch_tokens, top_k=_index.size)
    sketch_by_id = {result["id"]: result["score"] for result in sketch_only}
    for rank, idx in enumerate(ranked[:top_k], start=1):
        article = _index.articles[idx]
        article_id = article.get("id")
        results.append(
            {
                "rank": rank,
                "id": article_id,
                "title": article.get("title", ""),
                "score": float(combined[idx]),
                "plain_score": float(plain_by_id.get(article_id, 0.0)),
                "sketch_score": float(sketch_by_id.get(article_id, 0.0)),
                "snippet": make_snippet(str(article.get("body", ""))),
            }
        )
    return {
        "results": results,
        "fallback_used": fallback_used,
        "trace": {
            "plain_tokens": tokenize(query),
            "generated_terms": generated_terms,
            "accepted_terms": accepted_terms,
            "rejected_terms": validation["rejected"],
            "hallucination_rate": validation["hallucination_rate"],
            "tau": tau,
            "weight": weight,
        },
    }


def sira_retrieve(*args, **kwargs) -> dict[str, Any]:
    """Backward-compatible alias for older SIRA-named callers."""
    return evolved_retrieve(*args, **kwargs)
