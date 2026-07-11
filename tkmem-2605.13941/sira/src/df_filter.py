"""Document-frequency validation for generated sketch terms."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.index import tokenize


def load_df_store(path: str | Path = "data/df_store.json") -> dict[str, int]:
    with Path(path).open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return {str(term): int(count) for term, count in data.items()}


def validate_sketch_terms(
    generated_terms: list[str],
    df_store: dict[str, int],
    corpus_size: int,
    tau: float = 0.01,
) -> dict[str, Any]:
    threshold = max(1, int(tau * corpus_size))
    accepted: list[str] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()

    for term in generated_terms:
        normalized = " ".join(tokenize(term))
        if not normalized:
            rejected.append({"term": term, "reason": "empty_after_tokenization", "df": 0})
            continue
        if normalized in seen:
            rejected.append({"term": term, "reason": "duplicate", "df": df_store.get(normalized, 0)})
            continue
        seen.add(normalized)
        tokens = tokenize(normalized)
        term_df = max((df_store.get(token, 0) for token in tokens), default=0)
        if term_df <= 0:
            rejected.append({"term": term, "reason": "absent_from_corpus", "df": term_df})
        elif term_df > threshold:
            rejected.append({"term": term, "reason": "df_over_threshold", "df": term_df})
        else:
            accepted.append(normalized)

    hallucination_rate = len(rejected) / len(generated_terms) if generated_terms else 0.0
    return {
        "accepted": accepted,
        "rejected": rejected,
        "threshold": threshold,
        "hallucination_rate": hallucination_rate,
    }
