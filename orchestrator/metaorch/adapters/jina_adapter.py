"""MM_SEARCH — Jina ek_search contract: multimodal enterprise knowledge search."""

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


class JinaAdapter:
    kind = StageKind.MM_SEARCH
    name = "jina-ek-search"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "MM_SEARCH.validate_inputs"
        _require_keys(inputs, ("query_text", "n_results", "modality_filter", "source_filter", "acl_groups"), where)
        _require_str(inputs, "query_text", where)
        _require_int(inputs, "n_results", where, min_value=1)
        _require_list(inputs, "modality_filter", where)
        _require_list(inputs, "source_filter", where)
        _require_list(inputs, "acl_groups", where)

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "MM_SEARCH.validate_outputs"
        _require_keys(outputs, ("results", "total", "query_latency_ms", "backend_used", "embed_dim"), where)
        _require_list(outputs, "results", where)
        _require_int(outputs, "total", where, min_value=0)
        _require_float_checked = outputs.get("query_latency_ms")
        if not isinstance(_require_float_checked, (int, float)) or isinstance(_require_float_checked, bool):
            raise ContractError(f"{where}: 'query_latency_ms' must be float")
        _require_str(outputs, "backend_used", where, allowed=("stub", "local", "jina_api"))
        _require_int(outputs, "embed_dim", where, min_value=1)
        for i, r in enumerate(outputs["results"]):
            if not isinstance(r, dict):
                raise ContractError(f"{where}: results[{i}] must be dict")
            for k in ("id", "score", "modality", "source_system", "snippet"):
                if k not in r:
                    raise ContractError(f"{where}: results[{i}] missing '{k}'")
            score = r["score"]
            if not isinstance(score, (int, float)) or isinstance(score, bool) or not (0.0 <= score <= 1.0):
                raise ContractError(f"{where}: results[{i}].score must be float in [0,1], got {score!r}")
            _require_str(r, "modality", where + f".results[{i}]",
                         allowed=("text", "image", "audio", "video", "pdf"))

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        t0 = time.perf_counter()
        embed_dim = int(config.get("embed_dim", 384))
        n = inputs["n_results"]
        mods = inputs["modality_filter"] or ["text", "image", "audio", "video", "pdf"]
        srcs = inputs["source_filter"] or ["confluence", "notion", "figma", "loom"]
        results = []
        for i in range(min(n, 4)):
            results.append(
                {
                    "id": f"src:{srcs[i % len(srcs)]}:chunk_{i}",
                    "score": round(0.95 - 0.08 * i, 4),
                    "modality": mods[i % len(mods)],
                    "source_system": srcs[i % len(srcs)],
                    "snippet": f"result snippet #{i} for query '{inputs['query_text'][:48]}'",
                    "asset_url": f"https://{srcs[i % len(srcs)]}.example/asset/{i}",
                    "chunk_index": i,
                    "metadata": {"acl_groups": inputs["acl_groups"]},
                }
            )
        t1 = time.perf_counter()
        return {
            "results": results,
            "total": len(results),
            "query_latency_ms": round((t1 - t0) * 1000 + 1.5, 2),
            "backend_used": "stub",
            "embed_dim": embed_dim,
        }