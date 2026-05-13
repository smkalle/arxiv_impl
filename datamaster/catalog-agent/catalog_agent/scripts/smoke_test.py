"""
Smoke test: enriches N synthetic Food & Beverage SKUs using MockScorer + MockSKUStore.
Usage:
    python -m catalog_agent.scripts.smoke_test --skus 10 --dry-run
    python -m catalog_agent.scripts.smoke_test --skus 100
"""
import argparse
import asyncio
import random
import string
import sys
import time

import fakeredis.aioredis as fake_aioredis

from catalog_agent.api.models import EnrichRequest
from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.scorer.cataloglab import MockCatalogLabScorer
from catalog_agent.store.sku_store import MockSKUStore
from catalog_agent.sources.open_food_facts import OpenFoodFactsAdapter
from catalog_agent.sources.gs1 import GS1Adapter
from catalog_agent.artifacts.writer import ProvenanceWriter
from catalog_agent.agent.loop import run_enrichment_job
from catalog_agent.config import Settings


FOOD_CATEGORIES = ["beverages", "snacks", "dairy", "health", "food"]
BRANDS = ["NatureFoods", "HealthCo", "PureBev", "OrganicLife", "FreshFarm"]
PRODUCTS = [
    "Green Tea", "Protein Bar", "Yogurt", "Vitamin C Drink", "Oat Milk",
    "Energy Drink", "Dark Chocolate", "Almond Butter", "Sparkling Water",
    "Granola", "Kombucha", "Rice Crackers", "Miso Soup", "Soy Milk", "Matcha",
]


def _random_gtin() -> str:
    return "49" + "".join(random.choices(string.digits, k=11))


def generate_skus(n: int) -> list[dict]:
    skus = []
    for i in range(n):
        brand = random.choice(BRANDS)
        product = random.choice(PRODUCTS)
        cat = random.choice(FOOD_CATEGORIES)
        skus.append({
            "sku_id": f"SMOKE-{i+1:04d}",
            "gtin": _random_gtin(),
            "brand": brand,
            "title": f"{brand} {product}",
            "category_l2": cat,
            "attributes": {
                "title": f"{brand} {product}",
                "brand": brand,
            },
        })
    return skus


class MockOpenFoodFactsAdapter(OpenFoodFactsAdapter):
    """Returns synthetic data without hitting the network."""

    async def fetch(self, sku: dict) -> dict | None:
        category = sku.get("category_l2", "")
        if category not in {"beverages", "snacks", "dairy", "health", "food"}:
            return None
        return {
            "product_name": sku.get("title", ""),
            "brands": sku.get("brand", ""),
            "quantity": f"{random.choice([100, 250, 500, 1000])}ml",
            "ingredients_text": "water, natural flavors, citric acid",
            "allergens": "",
            "nutriments": {"energy-kcal_100g": random.randint(5, 120)},
            "packaging": random.choice(["PET bottle", "can", "carton", "glass"]),
            "countries": random.choice(["Japan", "US", "UK", "Germany"]),
            "labels": random.choice(["organic", "vegan", "gluten-free", ""]),
        }

    def source_url(self, sku: dict) -> str:
        return f"mock://open_food_facts/{sku.get('gtin', '')}"


class MockGS1Adapter(GS1Adapter):
    """Returns synthetic data without hitting the network."""

    def __init__(self):
        super().__init__(api_url="mock://gs1", api_key="")

    async def fetch(self, sku: dict) -> dict | None:
        return {
            "brandName": sku.get("brand", ""),
            "netContent": str(random.choice([50, 100, 200, 500, 1000])),
            "netContentUom": random.choice(["g", "ml", "oz"]),
            "countryOfOrigin": random.choice(["JP", "US", "GB", "DE"]),
            "gpcCategoryCode": "10000248",
            "productDescription": f"{sku.get('brand', '')} premium product",
        }

    def source_url(self, sku: dict) -> str:
        return f"mock://gs1/{sku.get('gtin', '')}"


async def run_smoke_test(n_skus: int, dry_run: bool, max_iterations: int = 10) -> dict:
    redis = fake_aioredis.FakeRedis(decode_responses=True)
    settings = Settings(
        cataloglab_url="",
        sku_store_url="",
        redis_url="redis://localhost:6379/0",
        artifact_dir="/tmp/catalog_agent_smoke",
        min_delta_threshold=2.0,
        max_iterations=max_iterations,
        agent_batch_size=3,
    )

    pool = ManifestStore(redis, ttl_seconds=3600)
    memory = CategoryInsightStore(redis)
    scorer = MockCatalogLabScorer()
    sku_store = MockSKUStore()
    sources = [MockOpenFoodFactsAdapter(), MockGS1Adapter()]
    writer = ProvenanceWriter(settings.artifact_dir)

    skus = generate_skus(n_skus)
    sku_store.seed(skus)

    request = EnrichRequest(
        sku_ids=[s["sku_id"] for s in skus],
        dry_run=dry_run,
        min_delta_threshold=2.0,
    )

    t0 = time.perf_counter()
    result = await run_enrichment_job(
        job_id="smoke-001",
        request=request,
        pool=pool,
        memory=memory,
        scorer=scorer,
        sku_store=sku_store,
        sources=sources,
        writer=writer,
        settings=settings,
    )
    elapsed = time.perf_counter() - t0

    await redis.aclose()
    return {
        "skus": n_skus,
        "dry_run": dry_run,
        "elapsed_s": round(elapsed, 2),
        "skus_processed": result.skus_processed,
        "skus_enriched": result.skus_enriched,
        "skus_rejected": result.skus_rejected,
        "avg_score_delta": result.avg_score_delta,
        "manifests_committed": result.manifests_committed,
        "status": result.status,
    }


def main():
    parser = argparse.ArgumentParser(description="CatalogAgent smoke test")
    parser.add_argument("--skus", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--iterations", type=int, default=10)
    args = parser.parse_args()

    result = asyncio.run(run_smoke_test(args.skus, args.dry_run, args.iterations))

    print("\n=== CatalogAgent Smoke Test ===")
    for k, v in result.items():
        print(f"  {k:25s}: {v}")

    avg = result.get("avg_score_delta") or 0.0
    if avg > 0:
        print(f"\n✓ PASS: avg_score_delta = {avg} > 0")
        sys.exit(0)
    else:
        print(f"\n✗ FAIL: avg_score_delta = {avg} (expected > 0)")
        sys.exit(1)


if __name__ == "__main__":
    main()
