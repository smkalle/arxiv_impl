import pytest
from catalog_agent.pool.models import Manifest, ManifestMeta
from catalog_agent.agent.black_node import run_black_node
from catalog_agent.artifacts.writer import ProvenanceWriter


def _make_manifest(sku_id="RAK-TEST-001", source="open_food_facts") -> Manifest:
    return Manifest(
        meta=ManifestMeta(
            source=source,
            source_url="https://world.openfoodfacts.org/api/v2/product/123.json",
            sku_id=sku_id,
            gtin="4901234567890",
            schema_fingerprint="fp123",
            coverage={"brand": True, "net_content": True, "ingredients": True},
            provenance="red_node_r1",
        ),
        data={
            "brand": "TestBrand",
            "net_content": "500ml",
            "ingredients": "water, green tea",
            "country_of_origin": "Japan",
        },
    )


async def test_black_node_commits_when_delta_sufficient(
    manifest_store, memory_store, mock_scorer, mock_sku_store, tmp_path
):
    m = _make_manifest()
    mid = await manifest_store.add(m)
    writer = ProvenanceWriter(artifact_dir=str(tmp_path))

    node_id, delta = await run_black_node(
        node_id="b1",
        manifest_id=mid,
        pool=manifest_store,
        scorer=mock_scorer,
        sku_store=mock_sku_store,
        memory=memory_store,
        writer=writer,
        job_id="job-test",
        min_delta=2.0,
        dry_run=False,
    )
    assert delta > 0
    committed = await manifest_store.get(mid)
    assert committed.meta.committed is True
    assert committed.meta.score_delta == delta


async def test_black_node_dry_run_does_not_commit(
    manifest_store, memory_store, mock_scorer, mock_sku_store, tmp_path
):
    m = _make_manifest()
    mid = await manifest_store.add(m)
    writer = ProvenanceWriter(artifact_dir=str(tmp_path))

    node_id, delta = await run_black_node(
        node_id="b2",
        manifest_id=mid,
        pool=manifest_store,
        scorer=mock_scorer,
        sku_store=mock_sku_store,
        memory=memory_store,
        writer=writer,
        job_id="job-dry",
        min_delta=2.0,
        dry_run=True,
    )
    assert delta > 0
    not_committed = await manifest_store.get(mid)
    assert not_committed.meta.committed is False


async def test_black_node_rejects_when_delta_below_threshold(
    manifest_store, memory_store, mock_scorer, mock_sku_store, tmp_path
):
    # SKU already has all the attributes external would provide
    mock_sku_store.seed([{
        "sku_id": "RAK-FULL",
        "gtin": "1111111111111",
        "brand": "TestBrand",
        "title": "TestBrand Green Tea 500ml",
        "category_l2": "beverages",
        "attributes": {
            "brand": "TestBrand",
            "net_content": "500ml",
            "ingredients": "water, green tea",
            "country_of_origin": "Japan",
            "title": "TestBrand Green Tea 500ml",
            "description": "Premium tea",
            "color": "green",
            "size": "large",
        },
    }])
    m = Manifest(
        meta=ManifestMeta(
            source="open_food_facts",
            source_url="https://world.openfoodfacts.org/api/v2/product/111.json",
            sku_id="RAK-FULL",
            schema_fingerprint="fp999",
            coverage={"brand": True},
            provenance="red_node_r1",
        ),
        data={"brand": "TestBrand"},  # only 1 field, already present
    )
    mid = await manifest_store.add(m)
    writer = ProvenanceWriter(artifact_dir=str(tmp_path))

    node_id, delta = await run_black_node(
        node_id="b3",
        manifest_id=mid,
        pool=manifest_store,
        scorer=mock_scorer,
        sku_store=mock_sku_store,
        memory=memory_store,
        writer=writer,
        job_id="job-reject",
        min_delta=2.0,
        dry_run=False,
    )
    assert delta < 2.0
    not_committed = await manifest_store.get(mid)
    assert not_committed.meta.committed is False


async def test_black_node_missing_manifest_returns_zero(
    manifest_store, memory_store, mock_scorer, mock_sku_store, tmp_path
):
    writer = ProvenanceWriter(artifact_dir=str(tmp_path))
    node_id, delta = await run_black_node(
        node_id="b4",
        manifest_id="nonexistent",
        pool=manifest_store,
        scorer=mock_scorer,
        sku_store=mock_sku_store,
        memory=memory_store,
        writer=writer,
        job_id="job-missing",
        min_delta=2.0,
        dry_run=False,
    )
    assert delta == 0.0
