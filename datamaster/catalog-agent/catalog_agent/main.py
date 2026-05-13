from contextlib import asynccontextmanager
from pathlib import Path

import redis.asyncio as aioredis
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from catalog_agent.config import get_settings
from catalog_agent.pool.manifest_store import ManifestStore
from catalog_agent.memory.category_insights import CategoryInsightStore
from catalog_agent.scorer.cataloglab import CatalogLabScorer, MockCatalogLabScorer
from catalog_agent.store.sku_store import SKUStore, MockSKUStore
from catalog_agent.sources.gs1 import GS1Adapter
from catalog_agent.sources.open_food_facts import OpenFoodFactsAdapter
from catalog_agent.sources.schema_org import SchemaOrgAdapter
from catalog_agent.artifacts.writer import ProvenanceWriter
from catalog_agent.api.routes import router


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    if settings.use_fake_redis:
        import fakeredis.aioredis as fake_aioredis
        redis = fake_aioredis.FakeRedis(decode_responses=True)
    else:
        redis = aioredis.from_url(settings.redis_url, decode_responses=True)

    app.state.settings = settings
    app.state.pool = ManifestStore(redis, ttl_seconds=settings.manifest_ttl_seconds)
    app.state.memory = CategoryInsightStore(redis)
    app.state.scorer = (
        MockCatalogLabScorer()
        if settings.use_mock_scorer
        else CatalogLabScorer(settings.cataloglab_url, settings.cataloglab_api_key, settings.cataloglab_batch_size)
    )
    app.state.sku_store = (
        MockSKUStore()
        if settings.use_mock_sku_store
        else SKUStore(settings.sku_store_url, settings.sku_store_api_key)
    )
    if settings.use_mock_sources:
        from catalog_agent.scripts.smoke_test import MockOpenFoodFactsAdapter, MockGS1Adapter
        app.state.sources = [MockOpenFoodFactsAdapter(), MockGS1Adapter()]
    else:
        app.state.sources = [
            GS1Adapter(settings.gs1_api_url, settings.gs1_api_key),
            OpenFoodFactsAdapter(settings.open_food_facts_url),
            SchemaOrgAdapter(),
        ]
    app.state.writer = ProvenanceWriter(settings.artifact_dir)

    # Seed mock store with sample data for dev
    if settings.use_mock_sku_store:
        _seed_mock_store(app.state.sku_store)

    yield
    await redis.aclose()


def _seed_mock_store(store: MockSKUStore) -> None:
    import random
    categories = ["beverages", "snacks", "dairy", "health", "food"]
    brands = ["TestBrand", "HealthCo", "NatureFoods", "PureBev", "OrganicLife"]
    products = [
        ("Green Tea", "4901234567890"),
        ("Protein Bar", "4901234567891"),
        ("Yogurt", "4901234567892"),
        ("Vitamin C", "4901234567893"),
        ("Oat Milk", "4901234567894"),
        ("Energy Drink", "4901234567895"),
        ("Dark Chocolate", "4901234567896"),
        ("Almond Butter", "4901234567897"),
        ("Sparkling Water", "4901234567898"),
        ("Granola", "4901234567899"),
    ]
    skus = []
    for i, (product, gtin) in enumerate(products):
        brand = brands[i % len(brands)]
        cat = categories[i % len(categories)]
        skus.append({
            "sku_id": f"DEMO-{i+1:03d}",
            "gtin": gtin,
            "brand": brand,
            "title": f"{brand} {product}",
            "category_l2": cat,
            "attributes": {
                "title": f"{brand} {product}",
                "brand": brand,
            },
        })
    store.seed(skus)


app = FastAPI(title="CatalogAgent", version="0.1.0", lifespan=lifespan)


# Inject request into route handlers that need app state
@app.middleware("http")
async def attach_request(request: Request, call_next):
    response = await call_next(request)
    return response


# Override route handler dependencies to pass request
from fastapi import APIRouter
from catalog_agent.api import routes as _routes

# Patch route handlers to receive the Request object
import inspect
from fastapi.routing import APIRoute

_original_router = router

app_router = APIRouter()


@app_router.post("/enrich", status_code=202)
async def enrich(body: _routes.EnrichRequest, request: Request):
    return await _routes.enrich(body, request=request)


@app_router.get("/job/{job_id}")
async def get_job(job_id: str):
    return await _routes.get_job(job_id)


@app_router.get("/jobs")
async def list_jobs():
    return await _routes.list_jobs()


@app_router.get("/pool")
async def get_pool(
    request: Request,
    category: str | None = None,
    source: str | None = None,
    min_delta: float | None = None,
    committed: bool | None = None,
    page: int = 1,
    page_size: int = 50,
):
    return await _routes.get_pool(
        request=request,
        category=category,
        source=source,
        min_delta=min_delta,
        committed=committed,
        page=page,
        page_size=page_size,
    )


@app_router.post("/rollback")
async def rollback(body: _routes.RollbackRequest, request: Request):
    return await _routes.rollback(body, request=request)


@app_router.get("/health")
async def health(request: Request):
    return await _routes.health(request=request)


@app_router.get("/memory/{category}")
async def get_memory(category: str, request: Request):
    return await _routes.get_memory(category, request=request)


app.include_router(app_router, prefix="/api")


@app.get("/", response_class=HTMLResponse)
async def root():
    ui_path = Path(__file__).parent / "ui" / "index.html"
    if ui_path.exists():
        return HTMLResponse(ui_path.read_text())
    return HTMLResponse("<h1>CatalogAgent</h1><p>UI not found. Visit <a href='/docs'>/docs</a></p>")


@app.get("/ui", response_class=HTMLResponse)
async def ui():
    ui_path = Path(__file__).parent / "ui" / "index.html"
    if ui_path.exists():
        return HTMLResponse(ui_path.read_text())
    return HTMLResponse("<h1>CatalogAgent UI</h1><p>UI not built yet.</p>")
