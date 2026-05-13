# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository purpose

This directory is the implementation workspace for **CatalogAgent v0.1.0**, a DataMaster-based autonomous data engineering agent derived from arXiv:2605.10906. The paper describes how a tree-structured agent loop — not model changes — delivers large quality gains by autonomously discovering and merging external data.

No implementation code exists yet. Primary artifacts:
- `datamaster_tutorial.md` — 7-step hands-on tutorial building a simplified DataMaster in Python (synthetic churn prediction task; uses pandas, sklearn, networkx)
- `CATALOGAGENT_SPEC.md` — Full build spec for the e-commerce catalog enrichment agent (10 steps, all testable before proceeding)

## What CatalogAgent does

Autonomous quality loop for e-commerce catalog SKUs:
1. **Red Node (Exploration)** — discovers attribute data from external sources (GS1, Open Food Facts, brand sites); writes to shared DataPool
2. **Black Node (Exploitation)** — merges pool data into SKU, scores impact with a **frozen** CatalogLab scorer, commits only if `score_delta ≥ MIN_DELTA_THRESHOLD`
3. **UCB-1 Scheduler** — selects next frontier node balancing exploration vs exploitation
4. **Backpropagation** — updates ancestor node rewards to inform future scheduling

## Architecture

```
catalog_agent/
├── agent/          # scheduler.py (UCBScheduler), red_node.py, black_node.py, loop.py
├── pool/           # ManifestStore — Redis-backed DataPool (metadata about discovered datasets)
├── memory/         # GlobalMemory — CategoryInsightStore (per-category source performance)
├── sources/        # HTTP adapters: GS1, Open Food Facts, schema.org
├── scorer/         # CatalogLabScorer + MockCatalogLabScorer (frozen — never retrains)
├── merge/          # Schema alignment + conflict resolution
├── api/            # FastAPI routes: /enrich, /job/{id}, /pool, /rollback
├── store/          # SKU read/write client
└── artifacts/      # Provenance writer (JSON + Parquet per committed enrichment)
```

DataTree is a NetworkX `DiGraph`. Exploration branches are red nodes; refinement nodes are black. The tree lives in `UCBScheduler`.

## Build order

Implement in this sequence (each step has its own tests before proceeding to the next):

1. Models + config (Pydantic v2, pydantic-settings)
2. ManifestStore (Redis async)
3. Source adapters (GS1, Open Food Facts; respx mocks for tests)
4. Schema alignment + conflict resolution
5. CatalogLabScorer + MockCatalogLabScorer
6. CategoryInsightStore (GlobalMemory)
7. Agent nodes — scheduler, red node, black node, loop
8. Provenance artifact writer
9. FastAPI layer
10. SKU Store client

## Implementation status

Code lives in `catalog-agent/`. Python 3.10+ compatible (uses `asyncio.gather` instead of `TaskGroup`).

## Commands

```bash
cd catalog-agent/

# Install deps (editable install requires pip>=23; use direct install if needed)
pip3 install -e ".[dev]"
# or without editable:
pip3 install fastapi uvicorn httpx "pydantic>=2.7" "pydantic-settings>=2.3" \
    networkx pandas pyarrow "redis[hiredis]" arq \
    pytest pytest-asyncio respx fakeredis

# Tests (all 42 pass)
PYTHONPATH=. python3 -m pytest tests/ -v

# Single test
PYTHONPATH=. python3 -m pytest tests/test_schema_align.py::test_align_gs1

# Smoke test (synthetic mock data, no network required)
PYTHONPATH=. python3 -m catalog_agent.scripts.smoke_test --skus 100 --iterations 15

# Dev server — full mock mode (no Redis, no external APIs, no CatalogLab)
PYTHONPATH=. CATALOGLAB_URL="" SKU_STORE_URL="" \
  USE_FAKE_REDIS=true USE_MOCK_SOURCES=true \
  python3 -m uvicorn catalog_agent.main:app --host 0.0.0.0 --port 8765 --reload

# Dev server — with real Redis (docker required)
docker run -d -p 6379:6379 redis:7-alpine
CATALOGLAB_URL="" SKU_STORE_URL="" USE_MOCK_SOURCES=true \
  PYTHONPATH=. python3 -m uvicorn catalog_agent.main:app --reload
```

## Dev flags

| Env var | Purpose |
|---|---|
| `USE_FAKE_REDIS=true` | Use in-process fakeredis — no Redis server required |
| `USE_MOCK_SOURCES=true` | Use synthetic mock adapters — no network access required |
| `CATALOGLAB_URL=""` | Auto-selects MockCatalogLabScorer |
| `SKU_STORE_URL=""` | Auto-selects MockSKUStore (seeded with 10 demo SKUs) |

## UI Dashboard

Served at `http://localhost:8765/` (also `/ui`). Features: job monitoring, data pool browser, memory insights, enrichment trigger form, rollback controls, health status. Auto-refreshes every 10 seconds.

## Runtime stack

Python 3.11+, FastAPI, asyncio + TaskGroup, NetworkX (DiGraph), pandas + pyarrow, Pydantic v2, Redis (redis-py async), arq (background jobs), httpx (async HTTP), OpenTelemetry SDK.

Test stack: pytest + pytest-asyncio, respx (HTTP mocks).

Explicitly excluded from production code: LangChain, LlamaIndex.

## Key invariants

- **Frozen scorer**: never retrain CatalogLab; only data inputs change.
- **Provenance first**: write provenance artifact before marking a manifest committed.
- **No blind writes**: always compute score delta before writing to SKU store.
- **Rollback always possible**: capture baseline SKU snapshot before any write.
- **Merchant-owned fields**: never overwrite `price`, `inventory`, or `primary_image`.

## Environment variables

```bash
CATALOGLAB_URL=https://cataloglab.internal
CATALOGLAB_API_KEY=...
SKU_STORE_URL=https://catalog.internal
SKU_STORE_API_KEY=...
REDIS_URL=redis://localhost:6379/0
GS1_API_KEY=...
UCB_EXPLORATION_C=1.0
AGENT_BATCH_SIZE=3
MIN_DELTA_THRESHOLD=2.0
MAX_ITERATIONS=50
ARTIFACT_BUCKET=s3://catalog-agent-artifacts
```

## MVP definition of done

- `/enrich` → `/job/{id}` round-trip works end-to-end with MockScorer
- Smoke test: 1,000 Food & Beverage SKUs, `avg_score_delta > 0`
- Rollback tested (enrich → `/rollback` → original attributes restored)
- Pool reuse demonstrated (second run on same SKUs hits cache)
- Provenance artifact written for every committed enrichment
- OpenTelemetry spans visible in local Jaeger for one job
