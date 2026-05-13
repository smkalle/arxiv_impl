# Changelog

All notable changes to `kb-ingestor` are documented here.
Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

---

## [0.1.0] — 2026-05-13

First production-ready release. Implements the full four-operator Arrow-native
ingestion pipeline derived from AAFLOW (arXiv:2605.02162), plus an admin and
ops dashboard.

### Pipeline (kb-ingestor)

- **OP-1 Load & Normalize** — `pyarrow.csv.read_csv` / `pyarrow.json.read_json`
  with source auto-detection, canonical 7-column schema enforcement, and
  configurable null policy (`drop` / `raise`)
- **OP-2 Chunk & Preprocess** — vectorized Arrow compute (`pc.utf8_slice_codeunits`,
  `pc.binary_join_element_wise`) with `min_chunk_chars` filter; no Python loops
- **OP-3 Embed (async batched)** — `asyncio.gather` + `asyncio.Semaphore` +
  `asyncio.to_thread` over `sentence-transformers`; configurable batch size and
  worker count
- **OP-4 FAISS Upsert** — sequential `IndexFlatL2.add` with zero-copy float32 view;
  contiguous `faiss_id` aligned to FAISS row positions

### Public API

```python
result = await ingest(source: pa.Table | Path, config: IngestConfig) -> IngestResult
```

Output artifacts: `tickets.arrow`, `index.faiss`, `run_summary.json` (includes `embed_dim`).

### CLI

```
kb-ingest run        --source <file> --out <dir>
kb-ingest validate   --source <file>
kb-ingest benchmark  --source <file> --rows N --runs N
```

Exit codes: 1 file-not-found · 2 schema · 3 embed-model · 4 FAISS-write · 5 runtime.
Config precedence: CLI flags > `.kb-ingestor.toml` > `~/.config/kb-ingestor/config.toml`.

### Error taxonomy

`IngestSchemaError` · `IngestNullError` · `EmbedModelError` · `EmbedDimMismatchError` ·
`FAISSWriteError` · `BatchProcessingError`

### Admin & Ops Dashboard

FastAPI backend + single-file vanilla JS frontend (no build step).
Start with `bash dashboard/start.sh` → open `http://localhost:8000`.

- **Run Dashboard** — KPI strip, live pipeline progress bar (OP-1→OP-4), throughput
  sparkline, recent runs table with status filter
- **Run Detail** — stage timeline chart, batch status grid, error detail panel with
  copy-JSON, serialization overhead chart, retry failed batches
- **New Ingestion Wizard** — 5-step form with pre-flight schema validation
- **Index Health** — FAISS index registry, Arrow ↔ FAISS consistency check,
  artifact downloads, soft-delete with 30s undo
- **Role-based access** — Admin / Ops / Read-only enforced at the API layer (JWT)
- **SSE real-time** — live stage and batch updates with exponential backoff reconnect

### Tests

- 56 unit + integration tests covering all four operators, CLI, and public API
- 102 dashboard tests (73 API contract + frontend structure, 29 Playwright headless
  browser tests)
- Benchmark gate: `kb-ingest benchmark` must show ≥ 2.0× speedup vs pandas baseline

### Known limitations / deferred

- OQ-1: multi-chunk sliding window deferred — truncation only in v0.1
- OQ-2: embedding model alignment with SIRA retrieval deferred
- Dashboard scheduler and alert rules deferred to v0.2
- Single-machine, single-deployment scope throughout
