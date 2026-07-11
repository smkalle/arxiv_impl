"""RETRIEVE — SIRA retrieval contract: ticket_text -> top-k KB articles + audit."""

from __future__ import annotations

import re
import time
from typing import Any

from metaorch.adapters.base import (
    _require_float,
    _require_int,
    _require_keys,
    _require_list,
    _require_str,
)
from metaorch.errors import ContractError
from metaorch.models import StageKind


def _this_tokenizer(text: str) -> set[str]:
    return {w.lower() for w in re.findall(r"[A-Za-z0-9]{2,}", text) if len(w) >= 2}


class SiraAdapter:
    kind = StageKind.RETRIEVE
    name = "sira"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "RETRIEVE.validate_inputs"
        _require_keys(inputs, ("ticket_text", "top_k", "tau", "weight_w", "corpus"), where)
        _require_str(inputs, "ticket_text", where)
        _require_int(inputs, "top_k", where, min_value=1)
        _require_float(inputs, "tau", where, min_value=0.0)
        _require_float(inputs, "weight_w", where, min_value=0.0)
        _require_list(inputs, "corpus", where)
        if not inputs["corpus"]:
            raise ContractError(f"{where}: 'corpus' must be non-empty")
        for i, art in enumerate(inputs["corpus"]):
            if not isinstance(art, dict) or "article_id" not in art or "enriched_body" not in art:
                raise ContractError(f"{where}: corpus[{i}] malformed (need article_id, enriched_body)")

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "RETRIEVE.validate_outputs"
        _require_keys(
            outputs,
            ("results", "sketch_terms_generated", "sketch_terms_validated", "sketch_terms_rejected",
             "fallback_used", "latency_ms"),
            where,
        )
        _require_list(outputs, "results", where)
        _require_list(outputs, "sketch_terms_generated", where)
        _require_list(outputs, "sketch_terms_validated", where)
        _require_list(outputs, "sketch_terms_rejected", where)
        if not isinstance(outputs["fallback_used"], bool):
            raise ContractError(f"{where}: 'fallback_used' must be bool")
        if outputs["fallback_used"] and "fallback_reason" not in outputs:
            raise ContractError(f"{where}: 'fallback_reason' required when fallback_used=true")
        _require_int(outputs, "latency_ms", where, min_value=0)
        # rejected ⊆ generated
        gen = set(outputs["sketch_terms_generated"])
        rej = set(outputs["sketch_terms_rejected"])
        if not rej.issubset(gen):
            raise ContractError(f"{where}: sketch_terms_rejected must be subset of generated")

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        t0 = time.perf_counter()
        ticket = inputs["ticket_text"]
        tau = inputs["tau"]
        weight_w = inputs["weight_w"]
        top_k = inputs["top_k"]
        corpus = inputs["corpus"]

        ticket_tokens = _this_tokenizer(ticket)
        # Sketch expansion: words from ticket longer than 5 chars, plus product hints.
        sketch_generated = sorted({w for w in ticket_tokens if len(w) > 5})
        # DF validation: keep terms appearing in >= tau * len(corpus) enriched_terms sets.
        if corpus and sketch_generated:
            threshold = max(1, int(tau * len(corpus)) or 1)
            df: dict[str, int] = {w: 0 for w in sketch_generated}
            for art in corpus:
                terms = set(art.get("enriched_terms", []))
                for w in sketch_generated:
                    if w in terms:
                        df[w] += 1
            validated = [w for w in sketch_generated if df[w] >= threshold]
            rejected = [w for w in sketch_generated if df[w] < threshold]
            fallback = False
            fallback_reason = None
        else:
            validated, rejected, fallback, fallback_reason = [], [], True, "empty-sketch"

        valid_set = set(validated)

        scored = []
        for art in corpus:
            terms = set(art.get("enriched_terms", []))
            orig_match = ticket_tokens & _this_tokenizer(art.get("enriched_body", ""))
            enrich_match = valid_set & terms
            score = len(orig_match) + weight_w * len(enrich_match)
            scored.append(
                {
                    "article_id": art["article_id"],
                    "title": art.get("title", ""),
                    "score": round(float(score), 4),
                    "matched_original_terms": sorted(orig_match),
                    "matched_enriched_terms": sorted(enrich_match),
                    "snippet": art.get("enriched_body", "")[:120],
                }
            )
        scored.sort(key=lambda r: r["score"], reverse=True)
        results = scored[: top_k]

        t1 = time.perf_counter()
        out = {
            "results": results,
            "sketch_terms_generated": sketch_generated,
            "sketch_terms_validated": validated,
            "sketch_terms_rejected": rejected,
            "fallback_used": fallback,
            "latency_ms": int((t1 - t0) * 1000) + 1,
        }
        if fallback_reason is not None:
            out["fallback_reason"] = fallback_reason
        return out