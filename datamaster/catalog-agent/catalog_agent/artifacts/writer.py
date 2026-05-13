import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


class ProvenanceWriter:
    """Writes provenance JSON + enriched parquet for each committed enrichment."""

    def __init__(self, artifact_dir: str = "./artifacts_local"):
        self._dir = Path(artifact_dir)

    def _job_dir(self, job_id: str) -> Path:
        d = self._dir / job_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def write_provenance(
        self,
        job_id: str,
        node_id: str,
        sku_id: str,
        manifest_id: str,
        baseline_sku: dict,
        enriched_sku: dict,
        score_delta: float,
        conflict_log: list[dict],
    ) -> str:
        job_dir = self._job_dir(job_id)

        baseline_attrs = baseline_sku.get("attributes", {})
        enriched_attrs = enriched_sku.get("attributes", {})

        attribute_deltas = {}
        for attr, new_val in enriched_attrs.items():
            old_val = baseline_attrs.get(attr)
            if old_val != new_val:
                entry = next(
                    (e for e in conflict_log if e["attribute"] == attr), {}
                )
                attribute_deltas[attr] = {
                    "before": old_val,
                    "after": new_val,
                    "source": entry.get("external_val"),
                }

        provenance = {
            "job_id": job_id,
            "node_id": node_id,
            "sku_id": sku_id,
            "manifest_id": manifest_id,
            "score_delta": score_delta,
            "committed_at": datetime.now(timezone.utc).isoformat(),
            "attribute_deltas": attribute_deltas,
            "conflict_log": conflict_log,
        }

        json_path = job_dir / f"provenance_{node_id}.json"
        json_path.write_text(json.dumps(provenance, indent=2, default=str))

        rows = [
            {
                "sku_id": sku_id,
                "attribute": attr,
                "before": str(v.get("before", "")),
                "after": str(v.get("after", "")),
                "score_delta": score_delta,
            }
            for attr, v in attribute_deltas.items()
        ]
        if rows:
            df = pd.DataFrame(rows)
            parquet_path = job_dir / f"enriched_{node_id}.parquet"
            df.to_parquet(parquet_path, index=False)

        return str(json_path)
