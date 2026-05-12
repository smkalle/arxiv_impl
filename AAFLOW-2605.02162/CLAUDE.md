# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository Purpose

This directory is the implementation workspace for **kb-ingestor v0.1.0**, a product derived from the AAFLOW paper (arXiv:2605.02162, "Scalable Patterns for Agentic AI Workflows"). The paper PDF is at `2605.02162v1.pdf`. The primary design artifact is the product spec at `AAFLOW-arXiv:2605.02162-spec-kb-ingestor.md`.

No implementation code exists yet — this is a spec-first repository at kickoff stage.

## What kb-ingestor Is

A zero-copy Arrow-native pipeline that ingests Zendesk CSV / Jira JSON support ticket exports into a queryable FAISS vector index. The core hypothesis: replacing the `df.to_list() → numpy → embed → copy` pattern with a pyarrow-native pipeline yields ≥2.5× throughput improvement on ≥10K tickets.

## Architecture

Four-operator DAG, each typed as `Op = (I, O, f, P)`:

1. **OP-1 Load & Normalize** — `Path | pa.Table → pa.Table` (canonical 7-column schema). Uses `pa.csv.read_csv` / `pa.json.read_json` directly (no pandas in hot path).
2. **OP-2 Chunk & Preprocess** — `pa.Table → pa.Table` (adds `chunk`, `chunk_index` columns). Arrow compute vectorized slice via `pc.utf8_slice_codeunits`, no Python loops.
3. **OP-3 Embed (async batched)** — `pa.Table → pa.Table` (adds `embedding` column). `ThreadPoolExecutor` + `asyncio.gather` with semaphore; batches dispatched concurrently; results merged with `pa.concat_tables`.
4. **OP-4 FAISS Upsert** — `pa.Table → (pa.Table, faiss.Index)` (adds `faiss_id` column). Sequential (IndexFlatL2 not thread-safe for add); zero-copy float32 view into FAISS.

Data plane stays `pa.Table` from OP-1 through OP-4 — no list/numpy casts between operators.

## Output Artifacts

Three files written to `--out` directory:
- `tickets.arrow` — Arrow IPC, uncompressed LZ4 by default (mmappable by SIRA)
- `index.faiss` — serialized FAISS index
- `run_summary.json` — metrics + `embed_dim` key (used by SIRA for discovery)

`faiss_id` column in the Arrow table is always contiguous integers matching FAISS row positions — this is the join key for SIRA retrieval.

## Public API

```python
result = await ingest(source: pa.Table | Path, config: IngestConfig) -> IngestResult
# result.table, result.index, result.metrics, result.artifacts
```

`IngestConfig` defaults: `batch_size=128`, `max_workers=4`, `embed_model="all-MiniLM-L6-v2"`, `max_chunk_chars=512`, `faiss_factory="Flat"`.

CLI entry point: `kb-ingest run|benchmark|validate`.

## Runtime Dependencies

`pyarrow≥15`, `faiss-cpu≥1.8`, `sentence-transformers≥3`, `numpy≥1.26`, `click≥8`, `rich≥13`, `tomllib` (stdlib 3.11+).

Dev/test: `pytest`, `pytest-asyncio`, `faker`, `pandas` (baseline benchmark only).

Explicitly excluded from production code: `langchain`, `llama-index`, `pycylon`, `ray`.

## Testing

Tests go in `tests/` with `pytest` + `pytest-asyncio`. Run all tests:
```
pytest
```
Run a single test:
```
pytest tests/test_ops.py::test_load_zendesk_csv
```

Test fixtures (`fixtures/zendesk_1k.csv`, `fixtures/jira_1k.json`) are generated — not real data:
```
make fixtures
```

CI performance gate: `kb-ingest benchmark --rows 1000 --runs 1` must show speedup ≥2.0× vs pandas baseline on every PR.

## Key Error Classes

`IngestSchemaError`, `IngestNullError`, `EmbedModelError`, `EmbedDimMismatchError`, `FAISSWriteError`, `BatchProcessingError` — all defined in the public package surface.

## Open Design Questions (unresolved at kickoff)

See spec §12. Critical before v0.1 cut: OQ-1 (multi-chunk sliding window vs truncation) and OQ-2 (embedding model alignment with SIRA's retrieval expectations).
