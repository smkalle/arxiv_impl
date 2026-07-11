# CatalogAgent

`datamaster/` contains the CatalogAgent implementation derived from arXiv `2605.10906`. The project is framed as an autonomous catalog enrichment system for e-commerce SKUs, where a tree-structured agent loop discovers external product attributes, merges them into the catalog, and only commits changes when a frozen scorer reports a positive score delta.

## Core business flow

The agent loop is built around four ideas:

1. **Red nodes** explore external data sources such as GS1, Open Food Facts, and schema.org-style sources.
2. **Black nodes** exploit discovered data by merging it into SKU records.
3. **UCB-1 scheduling** chooses which frontier node to expand next.
4. **Backpropagation** updates ancestor rewards so the scheduler can learn from previous outcomes.

The business rule that governs writes is important: the system commits only when the score improvement clears the minimum delta threshold. The scorer is intentionally frozen; quality should improve through data discovery and merge logic, not model retraining.

## Main modules

From `datamaster/catalog-agent/catalog_agent/`:

- `agent/` — scheduler, red node, black node, and loop coordination.
- `sources/` — source adapters for GS1, Open Food Facts, and schema.org.
- `merge/` — schema alignment and conflict resolution.
- `scorer/` — CatalogLab scorer implementations, including the mock scorer used in dev.
- `pool/` — manifest / data-pool persistence.
- `memory/` — category insight store used as global memory.
- `api/` — FastAPI routes for job control and inspection.
- `artifacts/` — provenance writer for committed enrichments.
- `store/` — SKU store client.
- `main.py` — application assembly and runtime bootstrap.

## Runtime modes

`main.py` selects between real and mock dependencies from settings:

- Fake Redis vs real Redis.
- Mock scorer vs CatalogLab scorer.
- Mock SKU store vs real SKU store.
- Mock sources vs live source adapters.

That makes the app usable in both development and production-like environments without changing the code path.

## UI / API surface

The app exposes a FastAPI service and a browser UI:

- API endpoints include `/api/enrich`, `/api/job/{id}`, `/api/jobs`, `/api/pool`, `/api/rollback`, `/api/health`, and `/api/memory/{category}`.
- The root `/` and `/ui` routes serve the management dashboard when the static UI exists.

The dashboard is not just cosmetic; the local docs describe it as the operator console for job monitoring, data-pool browsing, memory inspection, enrichment triggering, rollback control, and health status.

## Key invariants to preserve

- The scorer stays frozen.
- Provenance artifacts are written before a manifest is marked committed.
- Score delta must be computed before writing to the SKU store.
- Rollback must remain possible because the baseline SKU snapshot is captured before any write.
- Merchant-owned fields such as `price`, `inventory`, and `primary_image` must not be overwritten.

## Commands and validation

From `datamaster/catalog-agent/`:

```bash
PYTHONPATH=. python3 -m pytest tests/ -v
PYTHONPATH=. python3 -m catalog_agent.scripts.smoke_test --skus 100 --iterations 15
PYTHONPATH=. CATALOGLAB_URL="" SKU_STORE_URL="" USE_FAKE_REDIS=true USE_MOCK_SOURCES=true \
  python3 -m uvicorn catalog_agent.main:app --host 0.0.0.0 --port 8765 --reload
```

The README and `CLAUDE.md` also document a mock-mode development flow that removes the need for Redis, external APIs, or the real scorer.

## Watchouts for future changes

- Keep the scheduler/tree semantics aligned with the red/black node design; future edits should not collapse the tree into a simpler linear job runner.
- If you change the route list or dashboard behavior, update the operator guidance in `CLAUDE.md` as well.
- If you change source adapters or merge rules, check the test files for conflict-resolution and schema-alignment expectations.
- The project intentionally excludes LangChain and LlamaIndex from production code; avoid introducing them unless the scope changes.

## Source references

- `/datamaster/CLAUDE.md`
- `/datamaster/catalog-agent/pyproject.toml`
- `/datamaster/catalog-agent/catalog_agent/main.py`
- `/datamaster/catalog-agent/catalog_agent/api/routes.py`
- `/datamaster/catalog-agent/catalog_agent/agent/scheduler.py`
- `/datamaster/catalog-agent/catalog_agent/merge/conflict.py`
- `/datamaster/catalog-agent/tests/test_api.py`
