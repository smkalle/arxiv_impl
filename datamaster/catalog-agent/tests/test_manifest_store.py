import pytest
from catalog_agent.pool.models import Manifest, ManifestMeta


def _make_manifest(sku_id="sku-1", source="open_food_facts") -> Manifest:
    return Manifest(
        meta=ManifestMeta(
            source=source,
            source_url="https://world.openfoodfacts.org/api/v2/product/123.json",
            sku_id=sku_id,
            gtin="1234567890123",
            schema_fingerprint="abc123",
            coverage={"brand": True, "net_content": True, "ingredients": False},
            provenance="red_node_r1",
        ),
        data={"brand": "TestBrand", "net_content": "500ml"},
    )


async def test_add_and_get(manifest_store):
    m = _make_manifest()
    mid = await manifest_store.add(m)
    result = await manifest_store.get(mid)
    assert result is not None
    assert result.meta.sku_id == "sku-1"
    assert result.data["brand"] == "TestBrand"


async def test_get_missing_returns_none(manifest_store):
    assert await manifest_store.get("nonexistent") is None


async def test_mark_committed(manifest_store):
    m = _make_manifest()
    mid = await manifest_store.add(m)
    await manifest_store.mark_committed(mid)
    result = await manifest_store.get(mid)
    assert result.meta.committed is True


async def test_exists_for_sku_source(manifest_store):
    assert not await manifest_store.exists_for_sku_source("sku-1", "open_food_facts")
    m = _make_manifest()
    await manifest_store.add(m)
    assert await manifest_store.exists_for_sku_source("sku-1", "open_food_facts")
    assert not await manifest_store.exists_for_sku_source("sku-1", "gs1")


async def test_get_candidates_filter_committed(manifest_store):
    m1 = _make_manifest(sku_id="sku-1")
    m2 = _make_manifest(sku_id="sku-2")
    mid1 = await manifest_store.add(m1)
    await manifest_store.add(m2)
    await manifest_store.mark_committed(mid1)

    committed = await manifest_store.get_candidates(committed=True)
    assert len(committed) == 1
    assert committed[0].meta.sku_id == "sku-1"

    uncommitted = await manifest_store.get_candidates(committed=False)
    assert len(uncommitted) == 1
    assert uncommitted[0].meta.sku_id == "sku-2"


async def test_update_score_delta(manifest_store):
    m = _make_manifest()
    mid = await manifest_store.add(m)
    await manifest_store.update_score_delta(mid, 12.5)
    result = await manifest_store.get(mid)
    assert result.meta.score_delta == 12.5


async def test_rollback_snapshot(manifest_store):
    snapshot = {"sku_id": "sku-1", "attributes": {"brand": "old"}}
    await manifest_store.store_rollback_snapshot("sku-1", snapshot)
    result = await manifest_store.get_rollback_snapshot("sku-1")
    assert result["attributes"]["brand"] == "old"
