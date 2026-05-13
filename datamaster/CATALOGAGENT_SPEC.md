# CatalogAgent — Build Spec
**E-Commerce Catalog Quality Agent · DataMaster Framework**

---

## What This Is

An autonomous data agent that closes product attribute gaps in an e-commerce catalog by:
1. Discovering attribute data from external open-data sources (GS1, Open Food Facts, brand sites)
2. Merging discovered data with existing SKU records
3. Scoring the impact using a **frozen** quality scorer (CatalogLab API — never retrained)
4. Committing only enrichments that measurably improve the quality score

The model never changes. Only the data fed to it improves. This is the DataMaster principle.

---

## Repository Layout

```
catalog-agent/
├── SPEC.md                        ← this file
├── pyproject.toml
├── README.md
│
├── catalog_agent/
│   ├── __init__.py
│   ├── main.py                    ← FastAPI app entry point
│   ├── config.py                  ← Settings (pydantic-settings)
│   │
│   ├── agent/
│   │   ├── __init__.py
│   │   ├── scheduler.py           ← UCBScheduler + DataTree (NetworkX)
│   │   ├── red_node.py            ← ExternalDataDiscoverer
│   │   ├── black_node.py          ← AttributeMerger + CatalogLabScorer call
│   │   └── loop.py                ← Main agent loop (asyncio)
│   │
│   ├── pool/
│   │   ├── __init__.py
│   │   ├── manifest_store.py      ← DataPool: Redis-backed manifest store
│   │   └── models.py              ← Pydantic models: Manifest, ManifestMeta
│   │
│   ├── memory/
│   │   ├── __init__.py
│   │   └── category_insights.py  ← GlobalMemory: category enrichment patterns
│   │
│   ├── sources/
│   │   ├── __init__.py
│   │   ├── base.py                ← Abstract SourceAdapter
│   │   ├── gs1.py                 ← GS1 GEPIR adapter
│   │   ├── open_food_facts.py     ← Open Food Facts API adapter
│   │   └── schema_org.py          ← schema.org/Product JSON-LD crawler
│   │
│   ├── scorer/
│   │   ├── __init__.py
│   │   └── cataloglab.py          ← CatalogLab scorer client (frozen eval)
│   │
│   ├── merge/
│   │   ├── __init__.py
│   │   ├── schema_align.py        ← ontology ↔ external field mapping
│   │   └── conflict.py            ← Conflict resolution policy engine
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes.py              ← /enrich, /job, /pool, /rollback endpoints
│   │   └── models.py              ← Request/response Pydantic models
│   │
│   ├── store/
│   │   ├── __init__.py
│   │   └── sku_store.py           ← SKU read/write client (catalog API)
│   │
│   └── artifacts/
│       ├── __init__.py
│       └── writer.py              ← Provenance JSON + Parquet artifact writer
│
└── tests/
    ├── conftest.py
    ├── test_red_node.py
    ├── test_black_node.py
    ├── test_manifest_store.py
    ├── test_schema_align.py
    ├── test_conflict.py
    └── test_api.py
```

---

## Tech Stack

| Layer | Choice | Reason |
|---|---|---|
| Language | Python 3.11+ | Matches tutorial; async-native |
| Web framework | FastAPI | Async, auto-docs |
| Async HTTP | httpx (AsyncClient) | All source adapters use this |
| Agent loop | asyncio + TaskGroup | Parallel black nodes |
| Graph / tree | networkx | DataTree (DiGraph) |
| Data layer | pandas + pyarrow | SKU DataFrames, parquet artifacts |
| Validation | pydantic v2 | All models |
| Config | pydantic-settings | .env + env vars |
| Cache / pool | redis (redis-py async) | ManifestStore |
| Task queue | arq (asyncio-native) | Background enrichment jobs |
| Testing | pytest + pytest-asyncio | All layers |
| Observability | opentelemetry-sdk | Spans per SKU enrichment |

---

## Environment Variables

```bash
# .env (never commit)

# CatalogLab scorer (frozen — read-only)
CATALOGLAB_URL=https://cataloglab.internal.marketplace.com
CATALOGLAB_API_KEY=...
CATALOGLAB_BATCH_SIZE=50           # SKUs per scoring request

# SKU Store (catalog)
SKU_STORE_URL=https://catalog.internal.marketplace.com
SKU_STORE_API_KEY=...

# DataPool (Redis)
REDIS_URL=redis://localhost:6379/0
MANIFEST_TTL_DAYS=30

# External source APIs
GS1_API_URL=https://gepir.gs1.org/index.php/search-by-gtin
GS1_API_KEY=...
OPEN_FOOD_FACTS_URL=https://world.openfoodfacts.org/api/v2

# Agent loop
UCB_EXPLORATION_C=1.0              # exploration constant
AGENT_BATCH_SIZE=3                 # black nodes per red node
MIN_DELTA_THRESHOLD=2.0            # minimum score improvement to commit
MAX_ITERATIONS=50                  # per enrichment job

# Artifact storage
ARTIFACT_BUCKET=s3://catalog-agent-artifacts
ARTIFACT_PATH_PREFIX=prod

# ARQ worker
ARQ_REDIS_URL=redis://localhost:6379/1
```

---

## Core Data Models

Define these first in `catalog_agent/pool/models.py` and `catalog_agent/api/models.py`. All other modules import from here.

```python
# catalog_agent/pool/models.py

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any

class ManifestMeta(BaseModel):
    manifest_id: str                    # uuid4[:8]
    source: str                         # "gs1" | "open_food_facts" | "schema_org"
    source_url: str
    sku_id: str
    gtin: str | None = None
    schema_fingerprint: str             # sha256 of column names
    coverage: dict[str, bool]           # attribute_name -> found
    score_delta: float | None = None    # None until evaluated
    committed: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    provenance: str                     # "red_node_{node_id}"

class Manifest(BaseModel):
    meta: ManifestMeta
    data: dict[str, Any]               # raw discovered attributes
```

```python
# catalog_agent/api/models.py

from pydantic import BaseModel
from typing import Literal

class EnrichRequest(BaseModel):
    sku_ids: list[str] | None = None
    quality_filter: dict | None = None  # {"max_score": 65}
    categories: list[str] | None = None
    sources: list[str] | None = None
    min_delta_threshold: float = 2.0
    dry_run: bool = False

class EnrichResponse(BaseModel):
    job_id: str
    estimated_skus: int
    eta_seconds: int

class JobStatus(BaseModel):
    status: Literal["queued", "running", "completed", "failed"]
    skus_processed: int
    skus_enriched: int
    skus_rejected: int
    avg_score_delta: float | None
    manifests_committed: int
    provenance_artifact: str | None
    enriched_at: str | None
```

---

## Module Specifications

### `agent/scheduler.py` — UCBScheduler

```python
class UCBScheduler:
    """
    Maintains a NetworkX DiGraph (DataTree).
    Selects next node via UCB-1 formula.
    Triggers red-node discovery when frontier is exhausted.
    """

    def __init__(self, exploration_c: float = 1.0):
        self.G = nx.DiGraph()
        self.root_id = "root"
        self.G.add_node(self.root_id, type="root", score=0.0, visits=0, reward=0.0)
        self.exploration_c = exploration_c

    def add_node(self, parent_id: str, node_type: Literal["red", "black"]) -> str:
        """Add a new node, return node_id."""

    def get_frontier(self) -> list[str]:
        """Return leaf nodes not yet fully explored."""

    def select_node(self, iteration: int) -> str:
        """UCB-1: exploit = reward/visits; explore = C * sqrt(ln(i) / visits)."""

    def backpropagate(self, node_id: str, reward: float) -> None:
        """Walk path from node to root, increment visits + reward on each."""
```

**UCB formula:**
```
score(n) = reward(n)/visits(n) + C * sqrt(ln(total_iterations) / visits(n))
Unvisited nodes get score = inf (optimistic initialization)
```

---

### `agent/red_node.py` — ExternalDataDiscoverer

```python
async def run_red_node(
    node_id: str,
    sku_batch: list[dict],             # [{"sku_id": "...", "gtin": "...", ...}]
    sources: list[SourceAdapter],
    pool: ManifestStore,
    memory: CategoryInsightStore,
) -> list[str]:
    """
    For each SKU in batch:
      1. Check DataPool for existing manifest (cache hit → skip)
      2. Query each source adapter in parallel (httpx TaskGroup)
      3. Write each discovered dataset as Manifest to DataPool
      4. Return list of manifest_ids discovered

    Source priority order informed by memory.get_top_sources(category).
    Deduplicate: if pool already has manifest for (sku_id, source) within TTL, skip.
    """
```

---

### `agent/black_node.py` — AttributeMerger + Eval

```python
async def run_black_node(
    node_id: str,
    manifest_id: str,
    pool: ManifestStore,
    scorer: CatalogLabScorer,
    sku_store: SKUStore,
    merger: AttributeMerger,
    memory: CategoryInsightStore,
    min_delta: float,
    dry_run: bool,
) -> tuple[str, float]:
    """
    1. Load manifest from DataPool
    2. Load baseline SKU record from SKUStore
    3. Run AttributeMerger → candidate enriched SKU dict
    4. Score candidate with CatalogLabScorer → delta vs baseline
    5. If delta >= min_delta AND NOT dry_run:
         a. Write enriched SKU to SKUStore
         b. Write provenance artifact (JSON + parquet)
         c. Update manifest.committed = True
         d. Update memory with outcome
    6. Return (node_id, delta)
    """
```

---

### `merge/schema_align.py` — SchemaAligner

Purpose: map external source field names to attribute ontology keys.

```python
# Mapping registry — extend this dict to add new sources
FIELD_MAP: dict[str, dict[str, str]] = {
    "open_food_facts": {
        "product_name": "title",
        "brands": "brand",
        "quantity": "net_content",
        "ingredients_text": "ingredients",
        "allergens": "allergens",
        "nutriments.energy-kcal_100g": "nutrition.energy_kcal",
        "packaging": "packaging_type",
        "countries": "country_of_origin",
        "labels": "certifications",
    },
    "gs1": {
        "brandName": "brand",
        "netContent": "net_content",
        "netContentUom": "net_content_uom",
        "countryOfOrigin": "country_of_origin",
        "gpcCategoryCode": "category_gpc",
        "productDescription": "description",
    },
    "schema_org": {
        "name": "title",
        "brand.name": "brand",
        "color": "color",
        "size": "size",
        "material": "material",
        "description": "description",
        "mpn": "mpn",
        "gtin13": "gtin",
    },
}

class SchemaAligner:
    def align(self, source: str, raw: dict) -> dict:
        """
        Map raw source fields to ontology using FIELD_MAP.
        Unknown fields go to aligned["_unmapped"][original_key].
        Nested dot-notation keys (e.g. "nutriments.energy-kcal_100g") resolved recursively.
        Returns dict of {marketplace: value}.
        """
```

---

### `merge/conflict.py` — ConflictResolver

```python
# Default policy (configurable per attribute class)
CONFLICT_POLICY = {
    # Merchant wins — these are operational, not physical
    "price": "merchant",
    "inventory": "merchant",
    "primary_image": "merchant",
    "delivery_info": "merchant",
    # External wins — authoritative physical attributes
    "net_content": "external",
    "net_content_uom": "external",
    "ingredients": "external",
    "allergens": "external",
    "nutrition.*": "external",
    "country_of_origin": "external",
    "certifications": "external",
    # Gap-fill only — external fills only if merchant value is null/empty
    "description": "gap_fill",
    "brand": "gap_fill",
    "color": "gap_fill",
    "size": "gap_fill",
    "material": "gap_fill",
    "mpn": "gap_fill",
}

class ConflictResolver:
    def resolve(
        self,
        attribute: str,
        merchant_val: Any,
        external_val: Any,
        policy_override: dict | None = None,
    ) -> tuple[Any, str]:
        """
        Returns (resolved_value, decision_reason).
        decision_reason is logged to provenance artifact.
        """
```

---

### `pool/manifest_store.py` — ManifestStore

```python
class ManifestStore:
    """Redis HASH store. Key: f"manifest:{manifest_id}". TTL: MANIFEST_TTL_DAYS."""

    async def add(self, manifest: Manifest) -> str:
        """Serialize to JSON, write to Redis with TTL. Return manifest_id."""

    async def get(self, manifest_id: str) -> Manifest | None:
        """Deserialize from Redis. Return None if expired or missing."""

    async def get_candidates(
        self,
        sku_id: str | None = None,
        category: str | None = None,
        min_delta: float | None = None,
    ) -> list[Manifest]:
        """
        Scan pool for matching manifests.
        MVP: Redis SCAN + filter in Python.
        Phase 2: move filter to Postgres JSONB for scale.
        """

    async def mark_committed(self, manifest_id: str) -> None:
        """Set manifest.meta.committed = True."""

    async def exists_for_sku_source(self, sku_id: str, source: str) -> bool:
        """Check if fresh manifest exists for this (sku_id, source) pair."""
```

---

### `memory/category_insights.py` — CategoryInsightStore

```python
class CategoryInsightStore:
    """
    Append-only log of enrichment outcomes.
    Keyed by (category_l2, source).
    Persisted to Redis sorted set + JSON append log.
    """

    async def record_outcome(
        self,
        category_l2: str,
        source: str,
        score_delta: float,
        attributes_filled: list[str],
        committed: bool,
    ) -> None:
        """Append outcome. Update running avg delta for (category, source)."""

    async def get_top_sources(self, category_l2: str, top_n: int = 3) -> list[str]:
        """Return top N sources by avg score_delta for this category."""

    async def get_fill_rates(self, category_l2: str) -> dict[str, float]:
        """Return {attribute: fill_rate} for this category across all sources."""
```

---

### `scorer/cataloglab.py` — CatalogLabScorer

```python
class CatalogLabScorer:
    """
    Thin HTTP client wrapping the frozen CatalogLab quality scoring API.
    This is the ONLY evaluation oracle. It never changes.
    """

    async def score(self, sku: dict) -> float:
        """POST /score with single SKU dict. Return score 0-100."""

    async def score_batch(self, skus: list[dict]) -> list[float]:
        """POST /score/batch. Return scores in same order. Batch size from config."""

    async def score_delta(self, baseline_sku: dict, candidate_sku: dict) -> float:
        """Score both, return candidate_score - baseline_score."""
```

**Stub for local dev (no CatalogLab access):**
```python
class MockCatalogLabScorer(CatalogLabScorer):
    """
    Returns baseline_score + (number of non-null attributes added * 1.5).
    Use when CATALOGLAB_URL is not set or in pytest fixtures.
    """
```

---

### `api/routes.py` — FastAPI Routes

```python
POST /enrich
  Body: EnrichRequest
  → queues ARQ job, returns EnrichResponse (202)

GET /job/{job_id}
  → returns JobStatus

GET /pool
  Query params: category, source, min_delta, committed, page, page_size
  → returns list[ManifestMeta]

POST /rollback
  Body: {"manifest_id": "...", "sku_id": "..."}
  → reverts enriched attributes to pre-enrichment snapshot
  → marks manifest.committed = False
  → returns {"rolled_back": true, "sku_id": "..."}

GET /health
  → {"status": "ok", "redis": "ok", "cataloglab": "ok"}
```

---

### `artifacts/writer.py` — ProvenanceWriter

Every committed black node writes two artifacts:

```python
async def write_provenance(
    job_id: str,
    node_id: str,
    sku_id: str,
    manifest_id: str,
    baseline_sku: dict,
    enriched_sku: dict,
    score_delta: float,
    conflict_log: list[dict],          # [{attribute, merchant_val, external_val, decision}]
) -> str:
    """
    Writes:
      s3://{ARTIFACT_BUCKET}/{job_id}/provenance_{node_id}.json
      s3://{ARTIFACT_BUCKET}/{job_id}/enriched_{node_id}.parquet

    provenance JSON structure:
    {
      "job_id": "...",
      "node_id": "...",
      "sku_id": "...",
      "manifest_id": "...",
      "score_delta": 14.2,
      "committed_at": "2026-05-14T02:31:44Z",
      "attribute_deltas": {
        "ingredients": {"before": null, "after": "water, sugar...", "source": "open_food_facts"},
        "net_content": {"before": null, "after": "500ml", "source": "gs1"}
      },
      "conflict_log": [...]
    }

    Returns artifact S3 URI.
    """
```

---

## Agent Loop (`agent/loop.py`)

```python
async def run_enrichment_job(
    job_id: str,
    request: EnrichRequest,
    pool: ManifestStore,
    memory: CategoryInsightStore,
    scorer: CatalogLabScorer,
    sku_store: SKUStore,
    sources: list[SourceAdapter],
    settings: Settings,
) -> JobStatus:
    """
    Main loop. Pseudocode:

    scheduler = UCBScheduler(C=settings.ucb_exploration_c)
    sku_batch = await sku_store.get_batch(request)
    best_score = 0.0
    results = []

    for i in range(settings.max_iterations):
        node_id = scheduler.select_node(i)
        node_type = scheduler.G.nodes[node_id]["type"]

        if node_type in ("root", "red"):
            red_id = scheduler.add_node(node_id, "red")
            manifest_ids = await run_red_node(red_id, sku_batch, sources, pool, memory)

            # Spawn batch of black nodes (settings.agent_batch_size)
            async with asyncio.TaskGroup() as tg:
                tasks = [
                    tg.create_task(run_black_node(
                        scheduler.add_node(red_id, "black"),
                        mid, pool, scorer, sku_store, merger,
                        memory, request.min_delta_threshold, request.dry_run
                    ))
                    for mid in manifest_ids[:settings.agent_batch_size]
                ]

            for node_id, delta in [t.result() for t in tasks]:
                scheduler.backpropagate(node_id, delta)
                results.append((node_id, delta))

        else:  # black node from frontier
            node_id, delta = await run_black_node(...)
            scheduler.backpropagate(node_id, delta)
            results.append((node_id, delta))

    return build_job_status(job_id, results)
    """
```

---

## Source Adapters

All adapters inherit from `sources/base.py`:

```python
class SourceAdapter(ABC):
    source_name: str

    @abstractmethod
    async def fetch(self, sku: dict) -> dict | None:
        """
        Takes SKU dict with keys: sku_id, gtin, jan, ean, brand, title, category_l2.
        Returns raw attribute dict from source, or None if not found.
        """
```

### GS1 GEPIR (`sources/gs1.py`)
- Lookup by: `gtin` (EAN-13 / JAN-13)
- Endpoint: `GET {GS1_API_URL}?gtin={gtin}&lang=en`
- Auth: `X-API-Key` header
- Returns: brandName, netContent, countryOfOrigin, gpcCategoryCode, productDescription
- Handle 404 gracefully (GTIN not in registry)

### Open Food Facts (`sources/open_food_facts.py`)
- Lookup by: `gtin` (barcode)
- Endpoint: `GET {OFF_URL}/product/{gtin}.json`
- No auth required (public API)
- Parse: `response["product"]` dict
- Handle `status: 0` (product not found)
- Category filter: only call for category_l2 in food/beverage/health

### Schema.org Crawler (`sources/schema_org.py`)
- Lookup by: `brand` + `title` → construct brand site URL from GlobalMemory or Google search
- Fetch brand product page HTML
- Extract `<script type="application/ld+json">` blocks
- Parse `@type: "Product"` JSON-LD
- Fields: name, brand.name, color, size, material, description, mpn, gtin13
- Respect robots.txt; rate limit to 1 req/sec per domain

---

## Testing Strategy

### Unit tests (no external calls)
- `test_schema_align.py`: test FIELD_MAP alignment for each source with fixture dicts
- `test_conflict.py`: test each policy class (merchant_wins, external_wins, gap_fill) with null/non-null combinations
- `test_manifest_store.py`: mock Redis; test add/get/expire/exists_for_sku_source

### Integration tests (mock HTTP)
- `test_red_node.py`: respx mock for GS1 + OFF; verify manifests written to pool
- `test_black_node.py`: fixture manifest + MockCatalogLabScorer; verify delta computed, artifact written
- `test_api.py`: FastAPI TestClient; /enrich → /job/{id} flow with MockScorer + mock ARQ

### Fixtures (`conftest.py`)
```python
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
        }
    }

@pytest.fixture
def mock_scorer():
    return MockCatalogLabScorer()
```

---

## Build Order

Build in this sequence — each step is testable before proceeding:

```
Step 1  Models + config
        catalog_agent/pool/models.py
        catalog_agent/api/models.py
        catalog_agent/config.py
        → pytest: model validation tests

Step 2  ManifestStore
        catalog_agent/pool/manifest_store.py
        → pytest: test_manifest_store.py (mock Redis)

Step 3  Source adapters
        catalog_agent/sources/base.py
        catalog_agent/sources/gs1.py
        catalog_agent/sources/open_food_facts.py
        → pytest: test_red_node.py (respx mocks)

Step 4  Schema alignment + conflict resolution
        catalog_agent/merge/schema_align.py
        catalog_agent/merge/conflict.py
        → pytest: test_schema_align.py, test_conflict.py

Step 5  CatalogLab scorer + mock
        catalog_agent/scorer/cataloglab.py
        → pytest: score_delta with MockScorer

Step 6  CategoryInsightStore (GlobalMemory)
        catalog_agent/memory/category_insights.py

Step 7  Agent nodes
        catalog_agent/agent/scheduler.py
        catalog_agent/agent/red_node.py
        catalog_agent/agent/black_node.py
        catalog_agent/agent/loop.py
        → pytest: test_black_node.py, end-to-end smoke test

Step 8  Artifacts
        catalog_agent/artifacts/writer.py
        → local filesystem write in tests (skip S3 in CI)

Step 9  API layer
        catalog_agent/api/routes.py
        catalog_agent/main.py
        → pytest: test_api.py

Step 10 SKU Store client
        catalog_agent/store/sku_store.py
        MockSKUStore for all tests
```

---

## Running Locally (Mock Mode)

No external services required for initial build. Use mock implementations:

```bash
# Install
pip install -e ".[dev]"

# Start Redis (Docker)
docker run -d -p 6379:6379 redis:7-alpine

# Run with mocks (no CatalogLab, no real SKU store)
CATALOGLAB_URL="" SKU_STORE_URL="" uvicorn catalog_agent.main:app --reload

# Run tests
pytest tests/ -v

# Smoke test: enrich 10 SKUs using mock scorer
python -m catalog_agent.scripts.smoke_test --skus 10 --dry-run
```

---

## Definition of Done (MVP)

- [ ] All 10 build steps complete with passing tests
- [ ] `/enrich` → `/job/{id}` round-trip works end-to-end with MockScorer
- [ ] 1,000 Food & Beverage SKUs enriched in smoke test with real GS1 + OFF adapters
- [ ] avg_score_delta > 0 on smoke test cohort (any positive lift validates the loop)
- [ ] Rollback tested: enrichment applied → `/rollback` → original attributes restored
- [ ] Pool reuse: second run on same SKU set hits cache, no new crawls
- [ ] Provenance artifact written for every committed enrichment
- [ ] OpenTelemetry spans visible in local Jaeger for one enrichment job

---

## Key Constraints

- **Never call CatalogLab score endpoint** without a candidate SKU ready. Score only when a merge is complete.
- **Never write to SKU store** without a positive score delta AND `dry_run=False`.
- **Always write provenance** before marking a manifest as committed.
- **Merchant data is not overwritten** for price, inventory, or primary_image under any circumstance.
- **Rollback must always be possible** — baseline SKU snapshot is captured before any write.
