# UC-1 · Enterprise Knowledge Search — Iterative Implementation Plan

Each iteration is a **vertical slice**: end-to-end functional, testable, and demonstrable.  
Iterations build on each other. No iteration breaks a passing test from a prior one.

---

## Iteration 0 · Skeleton & Config
**Goal:** Project structure, config system, abstract interfaces, stub backend. Nothing real yet.  
**Testable:** `pytest` runs green. Config loads from env. Stub backend returns deterministic vectors.

### Files
```
app/
  config.py          — Settings (pydantic-settings), load .env
  models.py          — Document, Chunk, SearchRequest, SearchResponse dataclasses
  backends/
    base.py          — EmbeddingBackend ABC
    stub.py          — StubBackend (deterministic random vectors)
    factory.py       — get_backend(config) factory
tests/
  test_config.py     — env var loading, defaults
  test_stub_backend.py — embed() shape, dtype, L2-norm
```

### Gate
- `pytest tests/test_config.py tests/test_stub_backend.py` — all green
- `StubBackend().embed(["hello"])` returns shape `(1, embed_dim)`, float32, L2-norm ≈ 1.0

---

## Iteration 1 · Vector Store + Ingestion Core
**Goal:** Chroma integration, DocumentPreprocessor (text chunking), IngestionPipeline with idempotency.  
**Testable:** Ingest 3 text documents, query by text, get ranked results back.

### Files added
```
app/
  vector_store.py    — ChromaVectorStore (add, query, delete, count, stats)
  ingestion/
    preprocessor.py  — DocumentPreprocessor (text: chunk 512 tokens / 64 overlap)
    pipeline.py      — IngestionPipeline (batch, hash-check, retry, dead-letter log)
tests/
  test_vector_store.py  — add/query/delete/idempotency with stub backend
  test_preprocessor.py  — text chunking: count, overlap, token bounds
  test_pipeline.py      — ingest 3 docs → 6+ chunks → Chroma count verified
```

### Gate
- Ingest `data/samples/` (3 markdown files) → query "onboarding" → score > 0 returned
- Idempotency: ingest same files twice → count unchanged
- `pytest tests/test_vector_store.py tests/test_preprocessor.py tests/test_pipeline.py` green

---

## Iteration 2 · Filesystem Connector + FastAPI
**Goal:** Real connector reads local files (text, images). FastAPI exposes `/ingest`, `/search`, `/health`.  
**Testable:** `curl POST /ingest` → documents indexed. `curl POST /search` → JSON results.

### Files added
```
app/
  connectors/
    base.py          — BaseConnector ABC (scan() → Iterator[Document])
    filesystem.py    — FileSystemConnector (md, txt, pdf-stub, png, jpg)
  api.py             — FastAPI app: /ingest, /search, /health, /stats
  main.py            — uvicorn entry point
tests/
  test_filesystem_connector.py — scan samples/ → correct Document objects
  test_api.py        — TestClient: POST /ingest, POST /search, GET /health
data/
  samples/           — 6 synthetic sample files (3 text + 2 images + 1 mixed)
```

### Gate
- `GET /health` → `{"status": "ok"}`
- `POST /ingest {"source":"filesystem","path":"./data/samples"}` → `ingested >= 3`
- `POST /search {"query_text":"onboarding"}` → results with score > 0
- All prior tests still green

---

## Iteration 3 · Local Embedding Backend + Eval Framework
**Goal:** Real `all-MiniLM-L6-v2` model. Eval harness with golden pairs. Precision@k measured.  
**Testable:** Precision@5 ≥ 0.60 on golden set with real embeddings (small model, small corpus).

### Files added
```
app/
  backends/
    local.py         — LocalBackend (SentenceTransformer, bfloat16 if available)
  eval/
    harness.py       — EvalHarness: run golden set, return EvalReport
    metrics.py       — precision_at_k, recall_at_k, mrr, latency_percentiles
data/
  golden/
    golden_pairs.json — 10 golden query pairs mapped to sample docs
tests/
  test_local_backend.py  — embed shape, dtype, cosine similarity sanity
  test_eval_harness.py   — EvalHarness runs, returns EvalReport with P@5 > 0
  test_golden.py         — full golden eval: P@5 ≥ 0.60 with local backend
```

### Gate
- `LocalBackend().embed(["test"])` → shape `(1, 384)`, float32
- Golden eval: Precision@5 ≥ 0.60, MRR ≥ 0.50 on 10 pairs
- Latency p95 < 200ms per query on local backend
- All prior tests still green

---

## Iteration 4 · Dashboard (Human Validation UI)
**Goal:** Single-page HTML dashboard served by FastAPI. Ingest, search, eval, stats — all interactive.  
**Testable:** Open browser → ingest samples → search → see results → run eval → see metrics.

### Files added
```
dashboard/
  index.html         — self-contained SPA (HTML + CSS + vanilla JS, no build step)
                       Panels: Ingest · Search · Eval · Stats · Health
app/
  api.py             — add GET / (serve dashboard), GET /eval (run golden eval)
tests/
  test_dashboard_routes.py — GET / returns 200 HTML, GET /eval returns EvalReport JSON
```

### Dashboard panels
| Panel | Controls | Output |
|---|---|---|
| **Health** | auto-poll 5s | backend name, model, doc count, status dot |
| **Ingest** | path input + Ingest button | progress, ingested/skipped/failed counts |
| **Search** | text input + filters + Search button | ranked result cards with score badges |
| **Eval** | Run Eval button | P@1 P@3 P@5, MRR, p50/p95 latency table |
| **Stats** | auto-refresh | donut chart by modality, bar chart by source |

### Gate
- `GET /` returns dashboard HTML
- `GET /eval` returns JSON `EvalReport` with `precision_at_5` field
- Dashboard loads, all panels functional in browser
- All prior tests still green

---

## Iteration 5 · Jina API Backend + Image Support
**Goal:** `JinaAPIBackend` (graceful mock if no key). Image preprocessing. Image search working.  
**Testable:** Image files indexed. Text query returns image results. `EMBEDDING_BACKEND=jina_api` path tested with mock.

### Files added
```
app/
  backends/
    jina_api.py      — JinaAPIBackend (httpx async, retry, rate-limit aware)
  ingestion/
    preprocessor.py  — add image path: PIL resize → encode
tests/
  test_jina_backend.py   — mock httpx → verify request shape, response parsing
  test_image_ingest.py   — ingest PNG → chunk with modality=image → queryable
  test_backend_switch.py — env var EMBEDDING_BACKEND switches backend at factory
```

### Gate
- `EMBEDDING_BACKEND=jina_api` with mocked HTTP → correct embedding shape returned
- Image ingested → `POST /search {"query_text":"logo"}` → image result in top-5
- `GET /stats` → `by_modality` includes `"image": N`
- All prior tests still green

---

## Test Matrix (all iterations)

| Test file | Iter | What it proves |
|---|---|---|
| `test_config.py` | 0 | Config loads, env overrides work |
| `test_stub_backend.py` | 0 | Stub vectors: shape, dtype, norm |
| `test_vector_store.py` | 1 | Add/query/delete/idempotency |
| `test_preprocessor.py` | 1 | Text chunking bounds and overlap |
| `test_pipeline.py` | 1 | End-to-end ingest → Chroma count |
| `test_filesystem_connector.py` | 2 | Connector scans correct file types |
| `test_api.py` | 2 | All API endpoints functional |
| `test_local_backend.py` | 3 | Real model embed: shape, cosine sanity |
| `test_eval_harness.py` | 3 | Eval runs without error |
| `test_golden.py` | 3 | P@5 ≥ 0.60, MRR ≥ 0.50 |
| `test_dashboard_routes.py` | 4 | GET / and GET /eval work |
| `test_jina_backend.py` | 5 | Jina API mock: request/response |
| `test_image_ingest.py` | 5 | Image modality indexed and searchable |
| `test_backend_switch.py` | 5 | Factory switches on env var |

---

## Run Commands

```bash
# Setup
cd ek_search
cp .env.example .env      # edit EMBEDDING_BACKEND as needed

# Run all tests
pytest -v --tb=short

# Run single iteration tests
pytest tests/test_config.py tests/test_stub_backend.py -v

# Run server
uvicorn app.main:app --reload --port 8000

# Open dashboard
open http://localhost:8000

# Run eval via CLI
python -m app.eval.harness
```
