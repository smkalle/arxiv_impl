"""INGEST — AAFLOW kb-ingestor contract: zendesk/jira export -> Arrow table + FAISS index."""

from __future__ import annotations

from typing import Any

from metaorch.adapters.base import (
    _require_int,
    _require_keys,
    _require_str,
)
from metaorch.errors import ContractError
from metaorch.models import StageKind


class AaflowAdapter:
    kind = StageKind.INGEST
    name = "aaflow-kb-ingestor"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "INGEST.validate_inputs"
        _require_keys(inputs, ("source_path", "source_type", "batch_size", "embed_model"), where)
        _require_str(inputs, "source_path", where)
        _require_str(inputs, "source_type", where, allowed=("zendesk", "jira"))
        _require_int(inputs, "batch_size", where, min_value=1)
        _require_str(inputs, "embed_model", where)

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "INGEST.validate_outputs"
        _require_keys(outputs, ("arrow_path", "faiss_path", "run_summary", "table_schema"), where)
        _require_str(outputs, "arrow_path", where)
        _require_str(outputs, "faiss_path", where)
        if not isinstance(outputs["run_summary"], dict):
            raise ContractError(f"{where}: 'run_summary' must be dict")
        _require_int(outputs["run_summary"], "embed_dim", where, min_value=1)
        _require_int(outputs["run_summary"], "rows_ingested", where, min_value=0)
        if not isinstance(outputs["table_schema"], dict) or not outputs["table_schema"]:
            raise ContractError(f"{where}: 'table_schema' must be a non-empty dict")

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        rows = int(config.get("rows_ingested", 1000))
        embed_dim = int(config.get("embed_dim", 384))
        batch_size = inputs["batch_size"]
        batches = max(1, rows // batch_size + (1 if rows % batch_size else 0))
        return {
            "arrow_path": f"artifacts/{inputs['source_type']}_tickets.arrow",
            "faiss_path": f"artifacts/{inputs['source_type']}_index.faiss",
            "run_summary": {
                "rows_ingested": rows,
                "batches": batches,
                "throughput_rps": 250,
                "embed_dim": embed_dim,
                "source_type": inputs["source_type"],
                "elapsed_s": round(rows / 250.0, 3),
            },
            "table_schema": {
                "columns": [
                    {"name": "id", "type": "int64"},
                    {"name": "subject", "type": "string"},
                    {"name": "description", "type": "string"},
                    {"name": "chunk", "type": "string"},
                    {"name": "chunk_index", "type": "int32"},
                    {"name": "embedding", "type": f"list<float32[{embed_dim}]>"},
                    {"name": "faiss_id", "type": "int64"},
                ]
            },
        }