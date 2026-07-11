"""CATALOG — DataMaster CatalogAgent contract: UCB-1 SKU enrichment with score delta gating."""

from __future__ import annotations

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


class DataMasterAdapter:
    kind = StageKind.CATALOG
    name = "datamaster-catalog-agent"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "CATALOG.validate_inputs"
        _require_keys(
            inputs, ("sku_ids", "sources", "min_delta_threshold", "dry_run"), where
        )
        _require_list(inputs, "sku_ids", where)
        _require_list(inputs, "sources", where)
        _require_float(inputs, "min_delta_threshold", where, min_value=0.0)
        if not isinstance(inputs["dry_run"], bool):
            raise ContractError(f"{where}: 'dry_run' must be bool")

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "CATALOG.validate_outputs"
        _require_keys(
            outputs,
            ("job_id", "status", "skus_processed", "skus_enriched", "skus_rejected",
             "avg_score_delta", "manifests_committed", "provenance_artifact"),
            where,
        )
        _require_str(outputs, "job_id", where)
        _require_str(outputs, "status", where,
                    allowed=("queued", "running", "completed", "failed"))
        _require_int(outputs, "skus_processed", where, min_value=0)
        _require_int(outputs, "skus_enriched", where, min_value=0)
        _require_int(outputs, "skus_rejected", where, min_value=0)
        _require_int(outputs, "manifests_committed", where, min_value=0)
        avg = outputs["avg_score_delta"]
        if avg is not None and (not isinstance(avg, (int, float)) or isinstance(avg, bool)):
            raise ContractError(f"{where}: 'avg_score_delta' must be float|None")

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        skus = inputs["sku_ids"]
        dry_run = inputs["dry_run"]
        min_delta = inputs["min_delta_threshold"]
        # Fake: each SKU yields a +3.0 score delta (above default threshold 2.0).
        processed = len(skus)
        enriched = 0 if dry_run else processed
        rejected = 0
        committed = 0 if dry_run else enriched
        avg_delta = None if dry_run else (3.0 if processed else 0.0)
        if not dry_run and avg_delta is not None and avg_delta < min_delta:
            committed = 0
            enriched = 0
            rejected = processed
        return {
            "job_id": f"job-{int(time.time())}",
            "status": "completed",
            "skus_processed": processed,
            "skus_enriched": enriched,
            "skus_rejected": rejected,
            "avg_score_delta": avg_delta,
            "manifests_committed": committed,
            "provenance_artifact": None if dry_run else "artifacts/catalog/provenance.json",
        }