import time
from pathlib import Path
from typing import Optional

from src.df_filter import validate_sketch_terms
from src.index import CorpusIndex, tokenize
from src.sketch import generate_sketch


class IndexNotLoadedError(Exception):
    pass


_index: Optional[CorpusIndex] = None


def load_index(index_path: str | Path) -> None:
    global _index
    _index = CorpusIndex.load(index_path)


def _set_index(index: Optional[CorpusIndex]) -> None:
    global _index
    _index = index


def retrieve(query: str, top_k: int = 5) -> list[dict]:
    if _index is None or _index.bm25 is None:
        raise IndexNotLoadedError("Call load_index() before retrieve()")
    if not _index.articles:
        raise IndexNotLoadedError("Index contains no articles")

    tokens = tokenize(query)
    scores = _index.bm25.get_scores(tokens)

    ranked = sorted(enumerate(scores), key=lambda x: x[1], reverse=True)[:top_k]

    results = []
    for idx, score in ranked:
        if score > 0:
            art = _index.articles[idx]
            body = art.get("body") or art.get("original_body", "")
            results.append({
                "article_id": art["article_id"],
                "title": art["title"],
                "score": round(score, 4),
                "snippet": body[:200] + "..." if len(body) > 200 else body,
            })
    return results


def sira_retrieve(
    query: str,
    top_k: int = 5,
    w: float = 1.5,
    tau: float = 0.01,
    sketch_model: str | None = None,
) -> dict:
    if _index is None or _index.bm25 is None:
        raise IndexNotLoadedError("Call load_index() before sira_retrieve()")
    if not _index.articles:
        raise IndexNotLoadedError("Index contains no articles")

    t0 = time.perf_counter()

    orig_tokens = tokenize(query)
    scores_orig = _index.bm25.get_scores(orig_tokens)

    fallback_used = False
    sketch_terms = []
    try:
        if sketch_model:
            sketch_terms = generate_sketch(query, model=sketch_model)
        else:
            sketch_terms = generate_sketch(query)
    except Exception:
        fallback_used = True

    validated = []
    rejected = []
    rejected_reasons = []

    if not sketch_terms:
        fallback_used = True
        final_scores = scores_orig
    else:
        N = len(_index.articles)
        validation = validate_sketch_terms(sketch_terms, _index.df_counter, N, tau)
        validated = validation["validated"]
        rejected = validation["rejected"]
        rejected_reasons = validation["rejected_reasons"]

        if validated:
            scores_sketch = _index.bm25.get_scores(validated)
            final_scores = [s1 + w * s2 for s1, s2 in zip(scores_orig, scores_sketch)]
        else:
            final_scores = scores_orig

    ranked = sorted(enumerate(final_scores), key=lambda x: x[1], reverse=True)[:top_k]

    query_lower = query.lower()
    results = []
    for idx, score in ranked:
        if score > 0:
            art = _index.articles[idx]
            body = art.get("body") or art.get("original_body", "")
            doc_tokens = _index.tokenized[idx]

            matched_original = [t for t in set(orig_tokens) if t in doc_tokens]

            enriched_terms = art.get("enriched_terms", [])
            matched_enriched = []
            for et in enriched_terms:
                et_lower = et.lower()
                if et_lower in query_lower or et_lower in validated:
                    matched_enriched.append(et_lower)

            results.append({
                "article_id": art["article_id"],
                "title": art["title"],
                "score": round(score, 4),
                "snippet": body[:200] + "..." if len(body) > 200 else body,
                "matched_original_terms": matched_original,
                "matched_enriched_terms": matched_enriched,
            })

    latency_ms = int((time.perf_counter() - t0) * 1000)

    hallucination_rate = 0.0
    if sketch_terms:
        hallucination_rate = round(len(rejected) / len(sketch_terms), 2)

    return {
        "results": results,
        "sketch_terms_generated": sketch_terms,
        "sketch_terms_validated": validated,
        "sketch_terms_rejected": rejected,
        "fallback_used": fallback_used,
        "latency_ms": latency_ms,
        "hallucination_rate": hallucination_rate,
    }
