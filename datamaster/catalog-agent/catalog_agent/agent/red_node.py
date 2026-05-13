import asyncio
import hashlib

from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.pool.models import Manifest, ManifestMeta
from catalog_agent.sources.base import SourceAdapter
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.merge.schema_align import SchemaAligner

_aligner = SchemaAligner()

TARGET_ATTRIBUTES = [
    "brand", "net_content", "net_content_uom", "ingredients", "allergens",
    "nutrition.energy_kcal", "country_of_origin", "certifications",
    "description", "color", "size", "material", "mpn", "packaging_type",
]


async def run_red_node(
    node_id: str,
    sku_batch: list[dict],
    sources: list[SourceAdapter],
    pool: ManifestStore,
    memory: CategoryInsightStore,
) -> list[str]:
    manifest_ids: list[str] = []

    for sku in sku_batch:
        category = sku.get("category_l2", "")
        top_sources = await memory.get_top_sources(category)
        ordered_sources = sorted(
            sources,
            key=lambda s: top_sources.index(s.source_name) if s.source_name in top_sources else 99,
        )

        async def _fetch_one(adapter: SourceAdapter, _sku: dict) -> tuple[str, dict | None]:
            if await pool.exists_for_sku_source(_sku["sku_id"], adapter.source_name):
                return adapter.source_name, None  # cache hit
            try:
                raw = await adapter.fetch(_sku)
            except Exception:
                raw = None
            return adapter.source_name, raw

        tasks = [asyncio.create_task(_fetch_one(src, sku)) for src in ordered_sources]
        results = await asyncio.gather(*tasks)

        for src_name, raw in results:
            if raw is None:
                continue
            adapter = next(s for s in sources if s.source_name == src_name)
            aligned = _aligner.align(src_name, raw)
            if not aligned or (len(aligned) == 1 and "_unmapped" in aligned):
                continue

            coverage = _aligner.coverage(aligned, TARGET_ATTRIBUTES)
            fingerprint = _aligner.fingerprint(aligned)

            meta = ManifestMeta(
                source=src_name,
                source_url=adapter.source_url(sku),
                sku_id=sku["sku_id"],
                gtin=sku.get("gtin"),
                schema_fingerprint=fingerprint,
                coverage=coverage,
                provenance=f"red_node_{node_id}",
            )
            manifest = Manifest(meta=meta, data=aligned)
            mid = await pool.add(manifest)
            manifest_ids.append(mid)

    return manifest_ids
