import pytest
import pytest_asyncio
import fakeredis.aioredis as fake_aioredis

from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.scorer.cataloglab import MockCatalogLabScorer
from catalog_agent.store.sku_store import MockSKUStore
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.config import Settings


@pytest.fixture
def settings():
    return Settings(
        cataloglab_url="",
        sku_store_url="",
        redis_url="redis://localhost:6379/0",
        min_delta_threshold=2.0,
        artifact_dir="/tmp/catalog_agent_test_artifacts",
    )


@pytest_asyncio.fixture
async def redis_client():
    client = fake_aioredis.FakeRedis()
    yield client
    await client.aclose()


@pytest_asyncio.fixture
async def manifest_store(redis_client):
    return ManifestStore(redis_client, ttl_seconds=3600)


@pytest_asyncio.fixture
async def memory_store(redis_client):
    return CategoryInsightStore(redis_client)


@pytest.fixture
def mock_scorer():
    return MockCatalogLabScorer()


@pytest_asyncio.fixture
async def mock_sku_store():
    store = MockSKUStore()
    store.seed([
        {
            "sku_id": "RAK-TEST-001",
            "gtin": "4901234567890",
            "jan": "4901234567890",
            "brand": "TestBrand",
            "title": "TestBrand Green Tea 500ml",
            "category_l2": "beverages",
            "attributes": {
                "title": "TestBrand Green Tea 500ml",
                "brand": "TestBrand",
            },
        },
        {
            "sku_id": "RAK-TEST-002",
            "gtin": "4901234567891",
            "brand": "HealthCo",
            "title": "HealthCo Protein Bar 60g",
            "category_l2": "snacks",
            "attributes": {
                "title": "HealthCo Protein Bar 60g",
                "brand": "HealthCo",
            },
        },
    ])
    return store


@pytest.fixture
def sample_sku():
    return {
        "sku_id": "RAK-TEST-001",
        "gtin": "4901234567890",
        "jan": "4901234567890",
        "brand": "TestBrand",
        "title": "TestBrand Green Tea 500ml",
        "category_l2": "beverages",
        "attributes": {
            "title": "TestBrand Green Tea 500ml",
            "brand": "TestBrand",
        },
    }
