from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.scorer.cataloglab import BaseCatalogLabScorer
from catalog_agent.store.sku_store import BaseSKUStore
from catalog_agent.merge.conflict import ConflictResolver
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.artifacts.writer import ProvenanceWriter

_resolver = ConflictResolver()


async def run_black_node(
    node_id: str,
    manifest_id: str,
    pool: ManifestStore,
    scorer: BaseCatalogLabScorer,
    sku_store: BaseSKUStore,
    memory: CategoryInsightStore,
    writer: ProvenanceWriter,
    job_id: str,
    min_delta: float,
    dry_run: bool,
) -> tuple[str, float]:
    manifest = await pool.get(manifest_id)
    if manifest is None:
        return node_id, 0.0

    baseline_sku = await sku_store.get(manifest.meta.sku_id)
    if baseline_sku is None:
        return node_id, 0.0

    baseline_attrs = baseline_sku.get("attributes", {})
    merged_attrs, conflict_log = _resolver.merge(baseline_attrs, manifest.data)

    candidate_sku = dict(baseline_sku)
    candidate_sku["attributes"] = merged_attrs

    delta = await scorer.score_delta(baseline_sku, candidate_sku)
    await pool.update_score_delta(manifest_id, delta)

    attributes_filled = [
        entry["attribute"]
        for entry in conflict_log
        if entry["decision"] in ("gap_fill", "external_wins")
        and entry["resolved_val"] is not None
    ]

    if delta >= min_delta and not dry_run:
        await sku_store.store_rollback_snapshot(manifest.meta.sku_id, baseline_sku)
        await sku_store.update(manifest.meta.sku_id, merged_attrs)
        artifact_path = await writer.write_provenance(
            job_id=job_id,
            node_id=node_id,
            sku_id=manifest.meta.sku_id,
            manifest_id=manifest_id,
            baseline_sku=baseline_sku,
            enriched_sku=candidate_sku,
            score_delta=delta,
            conflict_log=conflict_log,
        )
        await pool.mark_committed(manifest_id)
        await memory.record_outcome(
            category_l2=baseline_sku.get("category_l2", "unknown"),
            source=manifest.meta.source,
            score_delta=delta,
            attributes_filled=attributes_filled,
            committed=True,
        )
    else:
        await memory.record_outcome(
            category_l2=baseline_sku.get("category_l2", "unknown"),
            source=manifest.meta.source,
            score_delta=delta,
            attributes_filled=attributes_filled,
            committed=False,
        )

    return node_id, delta
