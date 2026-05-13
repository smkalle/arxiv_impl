import asyncio
from datetime import datetime, timezone

from catalog_agent.api.models import EnrichRequest, JobStatus
from catalog_agent.agent.scheduler import UCBScheduler
from catalog_agent.agent.red_node import run_red_node
from catalog_agent.agent.black_node import run_black_node
from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.scorer.cataloglab import BaseCatalogLabScorer
from catalog_agent.store.sku_store import BaseSKUStore
from catalog_agent.sources.base import SourceAdapter
from catalog_agent.artifacts.writer import ProvenanceWriter
from catalog_agent.config import Settings


async def run_enrichment_job(
    job_id: str,
    request: EnrichRequest,
    pool: ManifestStore,
    memory: CategoryInsightStore,
    scorer: BaseCatalogLabScorer,
    sku_store: BaseSKUStore,
    sources: list[SourceAdapter],
    writer: ProvenanceWriter,
    settings: Settings,
) -> JobStatus:
    scheduler = UCBScheduler(exploration_c=settings.ucb_exploration_c)
    sku_batch = await sku_store.get_batch(request)

    results: list[tuple[str, float]] = []
    skus_enriched = 0
    skus_rejected = 0
    manifests_committed = 0
    last_artifact: str | None = None

    for i in range(settings.max_iterations):
        node_id = scheduler.select_node(i)
        node_type = scheduler.G.nodes[node_id]["type"]

        if node_type in ("root", "red"):
            red_id = scheduler.add_node(node_id, "red")
            manifest_ids = await run_red_node(
                node_id=red_id,
                sku_batch=sku_batch,
                sources=sources,
                pool=pool,
                memory=memory,
            )
            if not manifest_ids:
                break  # no new data found

            batch_size = min(settings.agent_batch_size, len(manifest_ids))
            black_tasks = []
            black_node_ids = []
            for mid in manifest_ids[:batch_size]:
                black_id = scheduler.add_node(red_id, "black")
                black_node_ids.append(black_id)
                black_tasks.append(
                    run_black_node(
                        node_id=black_id,
                        manifest_id=mid,
                        pool=pool,
                        scorer=scorer,
                        sku_store=sku_store,
                        memory=memory,
                        writer=writer,
                        job_id=job_id,
                        min_delta=request.min_delta_threshold,
                        dry_run=request.dry_run,
                    )
                )

            black_results = await asyncio.gather(*black_tasks, return_exceptions=False)

            for nid, delta in black_results:
                scheduler.backpropagate(nid, delta)
                results.append((nid, delta))
                if delta >= request.min_delta_threshold:
                    skus_enriched += 1
                    manifests_committed += 1
                else:
                    skus_rejected += 1

        else:
            # Re-evaluate a black node from the frontier using any uncommitted manifest
            candidates = await pool.get_candidates(committed=False)
            if not candidates:
                break
            manifest_id = candidates[0].meta.manifest_id
            nid, delta = await run_black_node(
                node_id=node_id,
                manifest_id=manifest_id,
                pool=pool,
                scorer=scorer,
                sku_store=sku_store,
                memory=memory,
                writer=writer,
                job_id=job_id,
                min_delta=request.min_delta_threshold,
                dry_run=request.dry_run,
            )
            scheduler.backpropagate(nid, delta)
            results.append((nid, delta))
            if delta >= request.min_delta_threshold:
                skus_enriched += 1
                manifests_committed += 1
            else:
                skus_rejected += 1

    deltas = [d for _, d in results if d > 0]
    avg_delta = sum(deltas) / len(deltas) if deltas else 0.0

    return JobStatus(
        job_id=job_id,
        status="completed",
        skus_processed=len(sku_batch),
        skus_enriched=skus_enriched,
        skus_rejected=skus_rejected,
        avg_score_delta=round(avg_delta, 3),
        manifests_committed=manifests_committed,
        enriched_at=datetime.now(timezone.utc).isoformat(),
    )
