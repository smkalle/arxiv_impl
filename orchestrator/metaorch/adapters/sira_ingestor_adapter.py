"""KB_ENRICH — SIRA KB Ingestor + SIRA enrich contract."""

from __future__ import annotations

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


class SiraIngestorAdapter:
    kind = StageKind.KB_ENRICH
    name = "sira-kb-ingestor"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "KB_ENRICH.validate_inputs"
        _require_keys(inputs, ("kb_articles", "ollama_model", "tau", "weight_w"), where)
        _require_list(inputs, "kb_articles", where)
        if not inputs["kb_articles"]:
            raise ContractError(f"{where}: 'kb_articles' must be non-empty")
        for i, art in enumerate(inputs["kb_articles"]):
            if not isinstance(art, dict):
                raise ContractError(f"{where}: kb_articles[{i}] must be dict")
            for k in ("article_id", "title", "body", "product_area", "last_updated"):
                if k not in art:
                    raise ContractError(f"{where}: kb_articles[{i}] missing '{k}'")
        _require_str(inputs, "ollama_model", where)
        _require_float(inputs, "tau", where, min_value=0.0)
        _require_float(inputs, "weight_w", where, min_value=0.0)

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "KB_ENRICH.validate_outputs"
        _require_keys(
            outputs,
            ("enriched_kb_path", "kb_index_path", "setup_summary", "enriched_corpus"),
            where,
        )
        _require_str(outputs, "enriched_kb_path", where)
        _require_str(outputs, "kb_index_path", where)
        if not isinstance(outputs["setup_summary"], dict):
            raise ContractError(f"{where}: 'setup_summary' must be dict")
        if "retrieval_defaults" not in outputs["setup_summary"]:
            raise ContractError(f"{where}: 'setup_summary.retrieval_defaults' missing")
        rd = outputs["setup_summary"]["retrieval_defaults"]
        if not isinstance(rd, dict):
            raise ContractError(f"{where}: 'retrieval_defaults' must be dict")
        for k in ("tau", "weight_w", "top_k"):
            if k not in rd:
                raise ContractError(f"{where}: 'retrieval_defaults.{k}' missing")
        if not isinstance(outputs["enriched_corpus"], list):
            raise ContractError(f"{where}: 'enriched_corpus' must be list")

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        arts = inputs["kb_articles"]
        n = len(arts)
        # Deterministic "enrichment": per article, derive enriched_terms from
        # title tokens longer than 4 chars + product_area.
        corpus = []
        enriched_total = 0
        for art in arts:
            terms = sorted(
                {w for w in (*art["title"].split(), art["product_area"]) if len(w) > 4}
            )
            enriched_total += len(terms)
            corpus.append(
                {
                    "article_id": art["article_id"],
                    "title": art["title"],
                    "enriched_body": f"{art['body']} [enriched: {', '.join(terms)}]",
                    "enriched_terms": terms,
                }
            )
        return {
            "enriched_kb_path": "artifacts/enriched_kb.jsonl",
            "kb_index_path": "artifacts/kb_index.pkl",
            "setup_summary": {
                "kb_articles": n,
                "enriched_terms_total": enriched_total,
                "elapsed_s": round(n * 0.012, 3),
                "retrieval_defaults": {
                    "tau": inputs["tau"],
                    "weight_w": inputs["weight_w"],
                    "top_k": int(config.get("top_k", 5)),
                },
            },
            "enriched_corpus": corpus,
        }