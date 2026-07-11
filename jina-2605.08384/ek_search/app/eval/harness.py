"""Eval framework — precision@k, recall@k, MRR, latency percentiles."""
from __future__ import annotations
import json
import time
import logging
from pathlib import Path

import numpy as np

from app.models import EvalPair, EvalReport, SearchRequest

logger = logging.getLogger(__name__)


def _is_match(retrieved_id: str, expected_doc_ids: list[str]) -> bool:
    """Match a retrieved chunk id against expected document ids.
    Supports prefix, substring, and filename-stem matching.
    e.g. expected "src:filesystem:onboarding.md" matches
         retrieved "src:filesystem:onboarding.md:chunk_2"
    Also matches stem: "onboarding" matches any chunk of that file.
    """
    rid_lower = retrieved_id.lower()
    for exp in expected_doc_ids:
        exp_lower = exp.lower()
        # Prefix match
        if rid_lower.startswith(exp_lower):
            return True
        # Substring match
        if exp_lower in rid_lower:
            return True
        # Stem match: last colon-segment stripped of extension
        stem = exp_lower.split(":")[-1].rsplit(".", 1)[0]
        if stem and stem in rid_lower:
            return True
    return False


def precision_at_k(retrieved_ids: list[str], expected_doc_ids: list[str], k: int) -> float:
    """Fraction of top-k results that match any expected document id."""
    top_k = retrieved_ids[:k]
    hits = sum(1 for rid in top_k if _is_match(rid, expected_doc_ids))
    return hits / k if k else 0.0


def recall_at_k(retrieved_ids: list[str], expected_doc_ids: list[str], k: int) -> float:
    top_k = retrieved_ids[:k]
    hits = sum(1 for exp in expected_doc_ids
               if any(_is_match(rid, [exp]) for rid in top_k))
    return hits / len(expected_doc_ids) if expected_doc_ids else 0.0


def reciprocal_rank(retrieved_ids: list[str], expected_doc_ids: list[str]) -> float:
    for i, rid in enumerate(retrieved_ids, start=1):
        if _is_match(rid, expected_doc_ids):
            return 1.0 / i
    return 0.0


def load_golden_pairs(path: str | Path) -> list[EvalPair]:
    path = Path(path)
    if not path.exists():
        return []
    data = json.loads(path.read_text())
    return [
        EvalPair(
            id=d["id"],
            query_text=d["query_text"],
            expected_doc_ids=d["expected_doc_ids"],
            modality=d.get("modality", "text"),
        )
        for d in data
    ]


class EvalHarness:

    def __init__(self, search_fn, golden_path: str | Path = "data/golden/golden_pairs.json"):
        """search_fn: callable(SearchRequest) -> SearchResponse"""
        self.search_fn = search_fn
        self.golden_path = golden_path

    def run(self, n_results: int = 5) -> EvalReport:
        pairs = load_golden_pairs(self.golden_path)
        if not pairs:
            logger.warning("No golden pairs found at %s", self.golden_path)
            return EvalReport(0, 0, 0, 0, 0, 0, 0, 0)

        p1s, p3s, p5s, r5s, rrs, latencies = [], [], [], [], [], []
        details = []

        for pair in pairs:
            req = SearchRequest(query_text=pair.query_text, n_results=n_results)
            t0 = time.monotonic()
            resp = self.search_fn(req)
            lat_ms = (time.monotonic() - t0) * 1000

            retrieved = [r.id for r in resp.results]
            p1 = precision_at_k(retrieved, pair.expected_doc_ids, 1)
            p3 = precision_at_k(retrieved, pair.expected_doc_ids, 3)
            p5 = precision_at_k(retrieved, pair.expected_doc_ids, 5)
            r5 = recall_at_k(retrieved, pair.expected_doc_ids, 5)
            rr = reciprocal_rank(retrieved, pair.expected_doc_ids)

            p1s.append(p1); p3s.append(p3); p5s.append(p5)
            r5s.append(r5); rrs.append(rr); latencies.append(lat_ms)

            details.append({
                "id": pair.id,
                "query": pair.query_text,
                "p@1": round(p1, 3),
                "p@3": round(p3, 3),
                "p@5": round(p5, 3),
                "mrr": round(rr, 3),
                "latency_ms": round(lat_ms, 1),
                "top3": retrieved[:3],
                "expected": pair.expected_doc_ids,
            })

        lats = sorted(latencies)
        p50 = float(np.percentile(lats, 50)) if lats else 0.0
        p95 = float(np.percentile(lats, 95)) if lats else 0.0

        return EvalReport(
            precision_at_1=round(float(np.mean(p1s)), 4),
            precision_at_3=round(float(np.mean(p3s)), 4),
            precision_at_5=round(float(np.mean(p5s)), 4),
            recall_at_5=round(float(np.mean(r5s)), 4),
            mrr=round(float(np.mean(rrs)), 4),
            latency_p50_ms=round(p50, 1),
            latency_p95_ms=round(p95, 1),
            total_queries=len(pairs),
            details=details,
        )
