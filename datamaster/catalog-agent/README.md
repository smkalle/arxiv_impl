# CatalogAgent

**Autonomous e-commerce catalog enrichment · DataMaster framework · arXiv:2605.10906**

CatalogAgent closes product attribute gaps in e-commerce catalogs by autonomously discovering data from external open-data sources (GS1, Open Food Facts, schema.org), merging it with existing SKU records, and committing only enrichments that measurably improve a frozen quality score — the DataMaster principle: improve the data, never the model.

## Architecture

```
catalog_agent/
├── agent/          # UCBScheduler (DataTree), red node, black node, agent loop
├── pool/           # ManifestStore — Redis-backed DataPool
├── memory/         # CategoryInsightStore — per-category source performance
├── sources/        # Async HTTP adapters: GS1, Open Food Facts, schema.org
├── scorer/         # CatalogLabScorer + MockCatalogLabScorer (frozen — never retrained)
├── merge/          # SchemaAligner (FIELD_MAP) + ConflictResolver (policy engine)
├── api/            # FastAPI routes: /enrich, /job/{id}, /pool, /rollback, /health
├── store/          # SKUStore + MockSKUStore
├── artifacts/      # ProvenanceWriter — JSON + Parquet per committed enrichment
├── scripts/        # smoke_test.py
└── ui/             # Single-page management console (served at /)
```

The **DataTree** is a NetworkX `DiGraph`. Exploration branches are **red nodes** (discover external data); refinement nodes are **black nodes** (merge, score, commit or reject). Node selection uses UCB-1 balancing exploration vs. exploitation. Every committed enrichment writes a provenance artifact before the SKU record is updated.

## Quick start

**Requires Python 3.10+**

```bash
# Install dependencies
pip install fastapi uvicorn httpx "pydantic>=2.7" "pydantic-settings>=2.3" \
    networkx pandas pyarrow "redis[hiredis]" arq \
    pytest pytest-asyncio respx fakeredis

# Run tests (42 tests, no network or Redis required)
PYTHONPATH=. python3 -m pytest tests/ -v

# Smoke test — 100 synthetic Food & Beverage SKUs, MockScorer
PYTHONPATH=. python3 -m catalog_agent.scripts.smoke_test --skus 100

# Start server — full mock mode (no Redis, no external APIs)
PYTHONPATH=. CATALOGLAB_URL="" SKU_STORE_URL="" \
  USE_FAKE_REDIS=true USE_MOCK_SOURCES=true \
  python3 -m uvicorn catalog_agent.main:app --host 0.0.0.0 --port 8765

# Open http://localhost:8765  →  Management console
# Open http://localhost:8765/docs  →  Interactive API docs
```

## Development flags

| Env var | Default | Purpose |
|---|---|---|
| `USE_FAKE_REDIS=true` | `false` | In-process fakeredis — no Redis server needed |
| `USE_MOCK_SOURCES=true` | `false` | Synthetic mock adapters — no network needed |
| `CATALOGLAB_URL=""` | — | Auto-selects `MockCatalogLabScorer` |
| `SKU_STORE_URL=""` | — | Auto-selects `MockSKUStore` (seeded with 10 demo SKUs) |

For a real deployment, set:
```bash
CATALOGLAB_URL=https://cataloglab.internal
CATALOGLAB_API_KEY=...
SKU_STORE_URL=https://catalog.internal
SKU_STORE_API_KEY=...
REDIS_URL=redis://localhost:6379/0
GS1_API_KEY=...
```

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/api/enrich` | Start an enrichment job (async, 202) |
| `GET` | `/api/job/{id}` | Poll job status |
| `GET` | `/api/jobs` | List all jobs |
| `GET` | `/api/pool` | Browse the data pool (filterable by source, committed, min_delta) |
| `POST` | `/api/rollback` | Revert a committed enrichment to its pre-enrichment snapshot |
| `GET` | `/api/memory/{category}` | Top sources and fill rates for a category |
| `GET` | `/api/health` | Service health check |
| `GET` | `/` | Management console UI |

## Key invariants

- **Frozen scorer** — `CatalogLabScorer` is never retrained; only data inputs change
- **Provenance first** — artifact written before manifest is marked committed
- **No blind writes** — score delta computed before any SKU store update
- **Rollback always possible** — baseline snapshot captured before every write
- **Merchant-owned fields** — `price`, `inventory`, `primary_image` are never overwritten

## Tests

```
42 passed in ~19s
```

| File | Coverage |
|---|---|
| `test_schema_align.py` | FIELD_MAP alignment for GS1, Open Food Facts, schema.org |
| `test_conflict.py` | All conflict policy classes (merchant wins, external wins, gap fill, wildcard) |
| `test_manifest_store.py` | Redis pool CRUD, TTL, rollback snapshots |
| `test_red_node.py` | Source adapter fetch + manifest pool write (respx mocks) |
| `test_black_node.py` | Merge + score + commit/reject/dry-run |
| `test_api.py` | Full `/enrich` → `/job/{id}` round-trip, rollback, health |

## Paper

Based on **DataMaster** (arXiv:2605.10906). The core idea: a tree-structured agent loop with UCB-1 scheduling delivers large quality gains over static pipelines by autonomously discovering and merging external data — without retraining the evaluation model.
