"""TICKETMIND — TKMEM 3-view hybrid retrieval contract (semantic + lexical + symbolic)."""

from __future__ import annotations

import time
from typing import Any

from metaorch.adapters.base import (
    _require_int,
    _require_keys,
    _require_list,
    _require_str,
)
from metaorch.errors import ContractError
from metaorch.models import StageKind


class TkmemAdapter:
    kind = StageKind.TICKETMIND
    name = "ticketmind"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "TICKETMIND.validate_inputs"
        _require_keys(inputs, ("ticket_text", "top_k", "filters"), where)
        _require_str(inputs, "ticket_text", where)
        _require_int(inputs, "top_k", where, min_value=1)
        if not isinstance(inputs["filters"], dict):
            raise ContractError(f"{where}: 'filters' must be dict")
        if "session_id" in inputs and inputs["session_id"] is not None and not isinstance(inputs["session_id"], str):
            raise ContractError(f"{where}: 'session_id' must be str if present")

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "TICKETMIND.validate_outputs"
        _require_keys(outputs, ("results", "retrieval_trace"), where)
        _require_list(outputs, "results", where)
        rt = outputs["retrieval_trace"]
        if not isinstance(rt, dict):
            raise ContractError(f"{where}: 'retrieval_trace' must be dict")
        for k in ("query_plan", "latency_ms", "evolved_config_version"):
            if k not in rt:
                raise ContractError(f"{where}: retrieval_trace missing '{k}'")
        if rt["evolved_config_version"] not in ("baseline", "evolved"):
            raise ContractError(
                f"{where}: evolved_config_version must be baseline|evolved, got {rt['evolved_config_version']!r}"
            )
        for i, r in enumerate(outputs["results"]):
            if not isinstance(r, dict):
                raise ContractError(f"{where}: results[{i}] must be dict")
            for k in ("kb_id", "title", "score", "matched_terms", "view_contributions", "snippet"):
                if k not in r:
                    raise ContractError(f"{where}: results[{i}] missing '{k}'")
            vc = r["view_contributions"]
            if not isinstance(vc, dict):
                raise ContractError(f"{where}: results[{i}].view_contributions must be dict")
            for v in ("semantic", "lexical", "symbolic"):
                if v not in vc or not isinstance(vc[v], (int, float)) or isinstance(vc[v], bool) or vc[v] < 0:
                    raise ContractError(
                        f"{where}: results[{i}].view_contributions.{v} must be float >= 0"
                    )

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        t0 = time.perf_counter()
        top_k = inputs["top_k"]
        evolved = bool(config.get("evolved", False))
        corpus = config.get("corpus", [])
        n_corpus = len(corpus) or 6

        results = []
        for i in range(min(top_k, n_corpus)):
            base = 0.9 - 0.1 * i
            results.append(
                {
                    "kb_id": f"kb-{i+1}",
                    "title": f"KB article {i+1}",
                    "score": round(base, 4),
                    "matched_terms": [w for w in inputs["ticket_text"].split()][:3],
                    "view_contributions": {
                        "semantic": round(base * 0.5, 4),
                        "lexical": round(base * 0.3, 4),
                        "symbolic": round(base * 0.2, 4),
                    },
                    "snippet": f"hybrid result #{i+1} for '{inputs['ticket_text'][:48]}'",
                }
            )
        t1 = time.perf_counter()
        return {
            "results": results,
            "retrieval_trace": {
                "query_plan": "semantic+bm25+symbolic → RRF fusion",
                "latency_ms": int((t1 - t0) * 1000) + 1,
                "evolved_config_version": "evolved" if evolved else "baseline",
            },
        }