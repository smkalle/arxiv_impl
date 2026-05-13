import asyncio
import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock

import fakeredis.aioredis as fake_aioredis

from catalog_agent.main import app
from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.scorer.cataloglab import MockCatalogLabScorer
from catalog_agent.store.sku_store import MockSKUStore
from catalog_agent.sources.open_food_facts import OpenFoodFactsAdapter
from catalog_agent.artifacts.writer import ProvenanceWriter
from catalog_agent.config import Settings


@pytest.fixture(autouse=True)
async def setup_app_state(tmp_path):
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    settings = Settings(
        cataloglab_url="",
        sku_store_url="",
        redis_url="redis://localhost:6379/0",
        artifact_dir=str(tmp_path),
        min_delta_threshold=2.0,
    )
    pool = ManifestStore(redis, ttl_seconds=3600)
    memory = CategoryInsightStore(redis)
    scorer = MockCatalogLabScorer()
    sku_store = MockSKUStore()
    sku_store.seed([
        {
            "sku_id": "TEST-001",
            "gtin": "4901234567890",
            "brand": "TestBrand",
            "title": "TestBrand Green Tea 500ml",
            "category_l2": "beverages",
            "attributes": {"title": "TestBrand Green Tea 500ml", "brand": "TestBrand"},
        }
    ])
    writer = ProvenanceWriter(str(tmp_path))

    app.state.settings = settings
    app.state.pool = pool
    app.state.memory = memory
    app.state.scorer = scorer
    app.state.sku_store = sku_store
    app.state.sources = [OpenFoodFactsAdapter()]
    app.state.writer = writer
    yield
    await redis.aclose()


async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["cataloglab"] == "mock"


async def test_enrich_returns_202():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/enrich", json={
            "sku_ids": ["TEST-001"],
            "dry_run": True,
        })
    assert resp.status_code == 202
    data = resp.json()
    assert "job_id" in data
    assert data["estimated_skus"] == 1


async def test_job_status_lifecycle():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/enrich", json={"sku_ids": ["TEST-001"], "dry_run": True})
        job_id = resp.json()["job_id"]

        # Give the background task time to complete
        await asyncio.sleep(0.5)

        resp2 = await client.get(f"/api/job/{job_id}")
    assert resp2.status_code == 200
    data = resp2.json()
    assert data["job_id"] == job_id
    assert data["status"] in ("queued", "running", "completed", "failed")


async def test_job_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/job/nonexistent-job-id")
    assert resp.status_code == 404


async def test_pool_endpoint():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/api/pool")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


async def test_rollback_not_found():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/api/rollback", json={
            "manifest_id": "m1",
            "sku_id": "NO-SNAPSHOT",
        })
    assert resp.status_code == 404


async def test_list_jobs():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        await client.post("/api/enrich", json={"dry_run": True})
        resp = await client.get("/api/jobs")
    assert resp.status_code == 200
    assert len(resp.json()) >= 1
