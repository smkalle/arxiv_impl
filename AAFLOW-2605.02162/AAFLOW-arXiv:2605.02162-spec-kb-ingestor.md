# Technical Product Spec: Support Ticket → KB Ingestor

**Product:** `kb-ingestor` v0.1.0  
**Status:** Draft — Ready for Engineering Review  
**Author:** AI Product  
**Last Updated:** 2026-05-11  
**Feeds:** SIRA Support Ticket → Resolution KB Prototype  
**AAFLOW Patterns:** Zero-Copy Data Plane · Async Batch · Operator DAG  

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [User Stories](#3-user-stories)
4. [Architecture Overview](#4-architecture-overview)
5. [Data Model](#5-data-model)
6. [Operator Pipeline Spec](#6-operator-pipeline-spec)
7. [API / Interface Contract](#7-api--interface-contract)
8. [Configuration](#8-configuration)
9. [Performance Requirements](#9-performance-requirements)
10. [Error Handling & Resilience](#10-error-handling--resilience)
11. [Testing Plan](#11-testing-plan)
12. [Open Questions](#12-open-questions)
13. [Appendix: Dependency Stack](#13-appendix-dependency-stack)

---

## 1. Problem Statement

### Context

The SIRA prototype (Support Ticket → Resolution KB) requires a high-throughput ingestion pipeline that converts raw support ticket exports (Zendesk CSV, Jira JSON) into a queryable vector index. Today, any ad-hoc ingestion code in this space follows the fragmented pattern critiqued by AAFLOW (arXiv:2605.02162): DataFrame → list → numpy → embed → copy into index. At scale this serialization tax dominates total latency — the LLM call is not the bottleneck, the data movement is.

### Pain Points

| Pain | Current State | Impact |
|---|---|---|
| Serialization overhead | `df.to_list()` + numpy casts at every stage | 3–5× unnecessary copy on 10K+ ticket batches |
| No reusable ingest contract | Ad-hoc scripts per data source | Blocks Commerce Analytics Agent Builder Discover + CatalogLab reuse |
| No benchmark baseline | Unknown throughput on ticket datasets | Can't size infra or set SLOs |
| SIRA feed dependency | SIRA has no clean upstream artifact | KB search quality degrades without fresh index |

### Hypothesis

A zero-copy Arrow-native pipeline with async batching will reduce end-to-end ingest latency by ≥2.5× versus the Pandas baseline on ≥10,000 tickets, and produce an Arrow IPC + FAISS index artifact that SIRA can consume directly with no further preprocessing.

---

## 2. Goals & Non-Goals

### Goals

- **G1** — Batch-ingest Zendesk CSV and Jira JSON exports into a queryable FAISS index with no intermediate list/numpy copies between pipeline stages.
- **G2** — Produce two output artifacts: an Arrow IPC file (ticket metadata + chunk + embedding columns) and a serialized FAISS index file, both loadable by SIRA in one call.
- **G3** — Demonstrate ≥2.5× throughput improvement over a Pandas baseline on a 10K-ticket benchmark.
- **G4** — Expose a CLI entry point (`kb-ingest`) and a Python importable API (`from kb_ingestor import ingest`) for use by Commerce Analytics Agent Builder and CatalogLab pipelines.
- **G5** — Ship with a benchmarking sub-command (`kb-ingest benchmark`) that produces a Markdown report consumable in design docs and team wikis.

### Non-Goals

- No real-time / streaming ingest (v0.1 is batch-only).
- No direct Zendesk/Jira API integration — input is export files only (deferred to v0.2).
- No multi-node / Cylon distributed execution (single-machine only in v0.1).
- No LLM re-ranking or generation — this is ingest only; SIRA handles retrieval + reasoning.
- No authentication or access control on output artifacts.
- No GUI or web interface.

---

## 3. User Stories

### Primary — SIRA Engineer

> **As a SIRA engineer**, I want to run `kb-ingest run --source tickets.csv --out ./kb-artifacts/` and have a fresh `index.faiss` + `tickets.arrow` ready for SIRA query in under 5 minutes for 10K tickets, so that I can update the KB on a daily schedule without writing ingest code myself.

**Acceptance criteria:**
- Command runs end-to-end with a Zendesk CSV and a Jira JSON export without modification.
- Output directory contains `index.faiss` and `tickets.arrow`.
- A `run_summary.json` is written with row count, batch count, elapsed time, and throughput (tickets/sec).
- Exit code 0 on success; non-zero with a human-readable error on failure.

### Secondary — Commerce Analytics Agent Builder Platform Engineer

> **As a Commerce Analytics Agent Builder platform engineer**, I want to import `from kb_ingestor import ingest` and pass an Arrow Table directly (without touching the CLI), so that I can wire kb-ingestor as an operator inside the platform pipeline without subprocess overhead.

**Acceptance criteria:**
- `ingest(source: pa.Table | Path, config: IngestConfig) -> IngestResult` is a documented public API.
- `IngestResult` exposes `.table: pa.Table`, `.index: faiss.Index`, `.metrics: dict`.
- No side effects other than optional file writes when `output_path` is set in config.

### Tertiary — AI Product / Engineering Lead

> **As an AI product lead**, I want `kb-ingest benchmark --rows 1000,5000,10000` to produce a Markdown table comparing Arrow pipeline vs Pandas baseline at each scale, so that I can include it in engineering design docs to justify Arrow adoption.

**Acceptance criteria:**
- Output is a valid Markdown table with columns: rows, baseline_s, arrow_s, speedup_x.
- Results also written to `benchmark_results.json` for programmatic use.
- Benchmark runs 3× at each scale and reports mean ± std.

---

## 4. Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        kb-ingestor v0.1                         │
│                                                                 │
│  Input Layer                                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ Zendesk CSV  │  │  Jira JSON   │  │  pa.Table (direct)   │  │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘  │
│         └─────────────────┴──────────────────────┘             │
│                           │                                     │
│                    OP-1: Load & Normalize                       │
│                    (source → pa.Table, typed schema)            │
│                           │                                     │
│                    OP-2: Chunk & Preprocess                     │
│                    (Arrow compute, no Python loops)             │
│                           │                                     │
│                    OP-3: Embed (async batched)                  │
│                    (ThreadPoolExecutor, Arrow view)             │
│                           │                                     │
│                    OP-4: FAISS Upsert                           │
│                    (zero-copy float32 view → index)             │
│                           │                                     │
│  Output Layer                                                   │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐  │
│  │ tickets.arrow│  │ index.faiss  │  │  run_summary.json    │  │
│  │ (Arrow IPC)  │  │ (serialized) │  │  (metrics)           │  │
│  └──────────────┘  └──────────────┘  └──────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### Key Design Decisions

| Decision | Choice | Rationale |
|---|---|---|
| In-memory data plane | `pyarrow.Table` throughout | Zero-copy handoff between ops; no list/numpy casts |
| Embed execution | `ThreadPoolExecutor(max_workers=N)` | CPU-bound; async wrapping via `asyncio.to_thread` |
| Batching | Configurable `batch_size` (default 128) | Bounded memory; overlaps I/O + compute |
| FAISS index type | `IndexFlatL2` (v0.1) | Exact search; no training needed; swappable to IVF in v0.2 |
| Chunking | `pc.utf8_slice_codeunits` (Arrow compute) | Vectorized, no Python loop, UTF-8 safe |
| Output format | Arrow IPC + FAISS binary | SIRA can mmap IPC; FAISS binary is standard |

---

## 5. Data Model

### 5.1 Input Schema — Zendesk CSV

Expected columns (tolerant loader — extra columns dropped):

| Column | Type | Required | Notes |
|---|---|---|---|
| `id` | string | Yes | Ticket ID |
| `subject` | string | Yes | Ticket title |
| `description` | string | Yes | Body text |
| `status` | string | No | open / solved / closed |
| `created_at` | string (ISO8601) | No | |
| `tags` | string | No | Comma-separated |
| `assignee_email` | string | No | Dropped by default |

### 5.2 Input Schema — Jira JSON

Expected top-level keys per issue object:

| Key | Type | Required | Mapped To |
|---|---|---|---|
| `key` | string | Yes | `id` |
| `fields.summary` | string | Yes | `subject` |
| `fields.description` | string/null | Yes | `description` |
| `fields.status.name` | string | No | `status` |
| `fields.created` | string | No | `created_at` |
| `fields.labels` | list[string] | No | `tags` (joined) |

### 5.3 Canonical Internal Schema (Arrow Table)

All sources normalize to this schema before OP-2:

| Column | Arrow Type | Description |
|---|---|---|
| `id` | `pa.string()` | Source ticket ID |
| `subject` | `pa.string()` | Title |
| `description` | `pa.string()` | Full body |
| `status` | `pa.string()` | Normalized status |
| `created_at` | `pa.timestamp('us')` | Parsed timestamp |
| `tags` | `pa.list_(pa.string())` | Tag list |
| `source` | `pa.string()` | `"zendesk"` or `"jira"` |

### 5.4 Output Schema (Arrow IPC — `tickets.arrow`)

Canonical schema + ingest-added columns:

| Column | Arrow Type | Description |
|---|---|---|
| *(all canonical columns)* | | |
| `chunk` | `pa.string()` | Preprocessed text slice (≤512 chars) |
| `chunk_index` | `pa.int32()` | Position within source ticket |
| `embedding` | `pa.list_(pa.float32())` | 384-dim MiniLM vector |
| `faiss_id` | `pa.int64()` | Row position in FAISS index |

---

## 6. Operator Pipeline Spec

Each operator follows the AAFLOW formal model: `Op_i = (I_i, O_i, f_i, P_i)` where `I` = input type, `O` = output type, `f` = transform function, `P` = communication pattern.

### OP-1: Load & Normalize

```
I:  Path (CSV | JSON) | pa.Table
O:  pa.Table (canonical schema)
f:  Source-specific parser → schema validation → cast
P:  Embarrassingly Parallel (per-file)
```

**Behavior:**
- Detect source type from file extension or explicit `source` param.
- For CSV: `pa.csv.read_csv()` with explicit `ConvertOptions` for type coercion.
- For JSON: `pa.json.read_json()` → field extraction → `pa.table()` cast.
- For `pa.Table` input: validate schema, add `source` column if absent, return.
- Missing required columns raise `IngestSchemaError` with column names listed.
- Null `description` rows are logged and dropped (configurable via `null_policy`).

**Performance note:** `pa.csv.read_csv` is 5–10× faster than `pd.read_csv` on large files and returns an Arrow Table directly (no copy).

---

### OP-2: Chunk & Preprocess

```
I:  pa.Table (canonical schema)
O:  pa.Table (+ chunk, chunk_index columns)
f:  Arrow compute vectorized slice + concat
P:  Embarrassingly Parallel
```

**Behavior:**
- Build `text_input` column: `subject + " " + description` via `pc.binary_join_element_wise`.
- Slice to `max_chunk_chars` (default 512) using `pc.utf8_slice_codeunits` — vectorized, no Python loop.
- v0.1: single chunk per ticket (first 512 chars). v0.2: sliding window with stride.
- Add `chunk_index` column (all zeros in v0.1; multi-chunk offset in v0.2).
- Filter out chunks shorter than `min_chunk_chars` (default 20) — noise guard.

---

### OP-3: Embed (Async Batched)

```
I:  pa.Table (with chunk column)
O:  pa.Table (+ embedding column)
f:  SentenceTransformer.encode → pa.array cast
P:  Embarrassingly Parallel, async-batched
```

**Behavior:**
- Slice input table into `batch_size` (default 128) sub-tables.
- For each batch: extract `chunk` column as numpy view (`to_numpy(zero_copy_only=False)`).
- Run `embedder.encode(chunks, convert_to_numpy=True, batch_size=batch_size)` in a thread via `asyncio.to_thread`.
- Cast result to `pa.list_(pa.float32())` and append as column.
- All batches dispatched concurrently via `asyncio.gather` with semaphore bound of `max_workers` (default 4).
- Merge batch results with `pa.concat_tables`.

**Model:** `sentence-transformers/all-MiniLM-L6-v2` (default). Configurable via `embed_model` param. Output dim must match FAISS index dim — mismatch raises `EmbedDimMismatchError`.

---

### OP-4: FAISS Upsert

```
I:  pa.Table (with embedding column)
O:  pa.Table (+ faiss_id column), faiss.Index
f:  zero-copy float32 view → index.add
P:  Sequential (FAISS IndexFlatL2 not thread-safe for add)
```

**Behavior:**
- Extract embedding column: `np.array(table["embedding"].to_pylist(), dtype=np.float32)`.
- Call `index.add(embeddings)` — FAISS takes ownership; no copy if float32 contiguous.
- Add `faiss_id` column as `pa.array(range(start_id, start_id + len(table)), type=pa.int64())`.
- `start_id` is 0 for fresh index, or `index.ntotal` if appending to existing.
- Index type: `faiss.IndexFlatL2(dim)` in v0.1. Configurable factory string in v0.2.

---

## 7. API / Interface Contract

### 7.1 CLI

```
kb-ingest run
  --source PATH          CSV or JSON file path (required)
  --out DIR              Output directory (default: ./kb_output)
  --batch-size INT       Embed batch size (default: 128)
  --max-workers INT      Async thread pool size (default: 4)
  --embed-model STR      SentenceTransformer model name (default: all-MiniLM-L6-v2)
  --max-chunk-chars INT  Max chars per chunk (default: 512)
  --append               Append to existing index in --out (default: overwrite)
  --quiet                Suppress progress output

kb-ingest benchmark
  --source PATH          Reference dataset path (required)
  --rows LIST            Comma-separated row counts to test (default: 1000,5000,10000)
  --runs INT             Repetitions per row count (default: 3)
  --out DIR              Output directory for results (default: ./benchmark_output)

kb-ingest validate
  --source PATH          Input file to validate schema
  --source-type STR      zendesk | jira (auto-detected if omitted)
```

**Exit codes:**

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Input file not found |
| 2 | Schema validation failure |
| 3 | Embedding model load failure |
| 4 | FAISS index write failure |
| 5 | Unexpected runtime error (see stderr) |

---

### 7.2 Python API

```python
from kb_ingestor import ingest, IngestConfig, IngestResult
import pyarrow as pa

# From file path
result: IngestResult = await ingest(
    source=Path("tickets.csv"),
    config=IngestConfig(
        batch_size=128,
        max_workers=4,
        embed_model="all-MiniLM-L6-v2",
        max_chunk_chars=512,
        output_path=Path("./kb_output"),   # None = in-memory only
    )
)

# From existing Arrow Table (Commerce Analytics Agent Builder pipeline use case)
result: IngestResult = await ingest(
    source=my_arrow_table,
    config=IngestConfig(output_path=None)
)

# IngestResult fields
result.table        # pa.Table — full output schema with embeddings
result.index        # faiss.Index — loaded, queryable
result.metrics      # dict: elapsed_s, rows_ingested, batches, throughput_rps
result.artifacts    # dict: arrow_path, faiss_path (None if output_path not set)
```

**`IngestConfig` dataclass:**

```python
@dataclass
class IngestConfig:
    batch_size: int = 128
    max_workers: int = 4
    embed_model: str = "all-MiniLM-L6-v2"
    max_chunk_chars: int = 512
    min_chunk_chars: int = 20
    null_policy: Literal["drop", "raise"] = "drop"
    faiss_factory: str = "Flat"           # IndexFlatL2 in v0.1
    output_path: Path | None = None
    source_type: Literal["zendesk", "jira", "auto"] = "auto"
    append: bool = False
```

---

### 7.3 SIRA Integration Contract

SIRA loads artifacts via:

```python
import pyarrow.ipc as ipc
import faiss

table = ipc.open_file("kb_output/tickets.arrow").read_all()
index = faiss.read_index("kb_output/index.faiss")

# Query: embed question → search index → retrieve table rows
q_emb = embedder.encode(["question"], convert_to_numpy=True).astype(np.float32)
distances, ids = index.search(q_emb, k=5)
results = table.take(ids[0].tolist())
```

**Contract guarantees from kb-ingestor:**
- `faiss_id` column in Arrow table is always contiguous integers matching FAISS row positions.
- Arrow IPC file uses uncompressed LZ4 by default (SIRA can mmap directly).
- Embedding dim is written to `run_summary.json` under `embed_dim` key.

---

## 8. Configuration

### 8.1 Config File (`.kb-ingestor.toml`)

```toml
[ingest]
batch_size = 128
max_workers = 4
embed_model = "all-MiniLM-L6-v2"
max_chunk_chars = 512
min_chunk_chars = 20
null_policy = "drop"

[output]
compress = false          # true = LZ4 IPC compression (slower load)
faiss_factory = "Flat"    # "IVF1024,Flat" for v0.2 ANN
```

CLI flags override config file values. Config file location: `$PWD/.kb-ingestor.toml` → `$HOME/.config/kb-ingestor/config.toml` (first found wins).

### 8.2 Environment Variables

| Variable | Default | Description |
|---|---|---|
| `KB_INGESTOR_EMBED_MODEL` | `all-MiniLM-L6-v2` | Override embed model |
| `KB_INGESTOR_MAX_WORKERS` | `4` | Thread pool size |
| `KB_INGESTOR_LOG_LEVEL` | `INFO` | DEBUG / INFO / WARNING |
| `TRANSFORMERS_CACHE` | HuggingFace default | Model cache directory |

---

## 9. Performance Requirements

### 9.1 Throughput SLO (v0.1)

| Dataset Size | Target Throughput | Max Elapsed |
|---|---|---|
| 1,000 tickets | ≥ 800 tickets/sec | < 2s |
| 5,000 tickets | ≥ 600 tickets/sec | < 10s |
| 10,000 tickets | ≥ 500 tickets/sec | < 25s |
| 50,000 tickets | ≥ 400 tickets/sec | < 130s |

*Baseline hardware: 8-core CPU, 16GB RAM, no GPU. MiniLM-L6-v2.*

### 9.2 Memory Budget

- Peak RSS must not exceed `(batch_size × embed_dim × 4 bytes × 3) + source_file_size × 2`.
- At batch_size=128, dim=384: ~600KB per batch of embeddings — negligible.
- Full 10K ticket Arrow Table (pre-embed): ~50MB estimate. Peak with embeddings: ~200MB.

### 9.3 Benchmark Methodology

The `kb-ingest benchmark` sub-command measures:

```
Stage timings captured:
  t_load      — OP-1: file read → Arrow Table
  t_preprocess — OP-2: chunk + preprocess
  t_embed     — OP-3: async embed (wall time)
  t_upsert    — OP-4: FAISS upsert
  t_total     — end-to-end

Baseline comparison:
  Baseline = pd.read_csv → .tolist() → SentenceTransformer.encode → faiss.add
  Arrow    = kb-ingestor full pipeline
  Speedup  = baseline_t_total / arrow_t_total
```

Report format (Markdown):

```markdown
## kb-ingestor Benchmark — all-MiniLM-L6-v2

| Rows  | Baseline (s) | Arrow (s) | Speedup |
|-------|-------------|-----------|---------|
| 1,000 | 2.41 ± 0.12 | 0.91 ± 0.04 | 2.65× |
| 5,000 | 11.8 ± 0.3  | 4.2 ± 0.1   | 2.81× |
|10,000 | 24.1 ± 0.6  | 8.3 ± 0.2   | 2.90× |
```

---

## 10. Error Handling & Resilience

### 10.1 Error Taxonomy

| Error Class | Condition | Behavior |
|---|---|---|
| `IngestSchemaError` | Required columns missing | Raise immediately; list missing columns |
| `IngestNullError` | Null description rows (if `null_policy="raise"`) | Raise with row IDs |
| `EmbedModelError` | Model download/load failure | Raise with model name + cache path |
| `EmbedDimMismatchError` | Model dim ≠ existing FAISS dim on append | Raise immediately; do not corrupt index |
| `FAISSWriteError` | Disk full / permission denied | Raise after partial write; temp file used |
| `BatchProcessingError` | Exception in async batch worker | Log batch ID + exception; re-raise after all batches complete |

### 10.2 Partial Failure Strategy

- On `BatchProcessingError`: collect all failed batch IDs, complete remaining batches, then raise a summary error listing failed batches and total rows lost.
- Failed row IDs written to `failed_rows.json` in output dir for re-run targeting.
- Successful output artifacts are still written if ≥90% of batches succeeded (configurable `min_success_rate`).

### 10.3 Idempotency

- Default behavior: `--out` directory is overwritten atomically (write to temp dir → rename).
- `--append` mode: checks `run_summary.json` embed dim matches current model before appending.

---

## 11. Testing Plan

### 11.1 Unit Tests

| Test | Coverage Target |
|---|---|
| `test_load_zendesk_csv` | Valid file, missing optional columns, null descriptions |
| `test_load_jira_json` | Valid file, nested field extraction, null description |
| `test_load_arrow_table` | Schema validation, missing required column |
| `test_chunk_vectorized` | Length enforcement, min_chunk_chars filter, UTF-8 edge cases |
| `test_embed_output_shape` | Correct dim, float32 dtype, Arrow list type |
| `test_faiss_id_contiguous` | faiss_id matches index row positions |
| `test_append_mode` | faiss_id continues from existing index.ntotal |
| `test_dim_mismatch_raises` | EmbedDimMismatchError on append with wrong model |
| `test_null_policy_drop` | Null rows dropped, row count in metrics |
| `test_null_policy_raise` | IngestNullError raised with row IDs |

### 11.2 Integration Tests

| Test | Description |
|---|---|
| `test_e2e_zendesk_1k` | Full pipeline on 1K-row Zendesk fixture, verify artifact files exist |
| `test_e2e_jira_1k` | Full pipeline on 1K-row Jira fixture |
| `test_sira_roundtrip` | Load output artifacts → FAISS search → verify top-1 result is sensible |
| `test_cli_run_exit_codes` | Each error condition returns correct exit code |
| `test_benchmark_output_format` | Benchmark produces valid Markdown + JSON |

### 11.3 Performance Regression Gate

CI runs `kb-ingest benchmark --rows 1000 --runs 1` on each PR. If speedup drops below 2.0× vs baseline, CI fails with a diff of timing breakdown.

### 11.4 Test Fixtures

- `fixtures/zendesk_1k.csv` — 1,000 rows, anonymized, includes intentional nulls (5%) and UTF-8 edge cases (Japanese, Arabic fields).
- `fixtures/jira_1k.json` — 1,000 issues in Jira export format, includes nested null descriptions.
- Both generated by a `make fixtures` script using Faker — no real ticket data in repo.

---

## 12. Open Questions

| # | Question | Owner | Target |
|---|---|---|---|
| OQ-1 | Should v0.1 support multi-chunk sliding window for long tickets (>512 chars)? Current spec truncates. Risk: retrieval quality degradation on long resolution notes. | AI Product + SIRA lead | Before v0.1 cut |
| OQ-2 | `all-MiniLM-L6-v2` is 384-dim. SIRA prototype was specced around BM25+LLM enrichment. Do we need to align embedding model with SIRA's semantic similarity expectations? | SIRA engineer | Before v0.1 cut |
| OQ-3 | Append mode: when ticket IDs already exist in the index, do we update (re-embed + replace) or skip? Update requires FAISS IDMap wrapper — adds complexity. | Engineering | v0.2 planning |
| OQ-4 | Is `run_summary.json` sufficient for SIRA to discover embed dim, or do we need a formal manifest (Arrow schema file + model card)? | SIRA engineer | Integration kickoff |
| OQ-5 | CatalogLab integration: they use Parquet, not Arrow IPC. Should the Python API expose a `to_parquet()` convenience method? | CatalogLab lead | v0.2 planning |
| OQ-6 | Benchmark target of 2.5× is conservative vs AAFLOW's 4.64× claim. Should we set a stretch target of 3.5× to stay aligned with the paper's positioning? | AI Product | Before kickoff |

---

## 13. Appendix: Dependency Stack

### Runtime Dependencies

| Package | Version | Role |
|---|---|---|
| `pyarrow` | ≥ 15.0 | Zero-copy data plane throughout |
| `faiss-cpu` | ≥ 1.8.0 | Vector index (CPU-only in v0.1) |
| `sentence-transformers` | ≥ 3.0 | Default embedding model |
| `numpy` | ≥ 1.26 | Float32 array interop (Arrow ↔ FAISS bridge only) |
| `click` | ≥ 8.0 | CLI framework |
| `rich` | ≥ 13.0 | Progress bars, benchmark reports |
| `tomllib` | stdlib (3.11+) | Config file parsing |

### Dev / Test Dependencies

| Package | Role |
|---|---|
| `pytest` + `pytest-asyncio` | Test runner + async test support |
| `faker` | Fixture generation |
| `pandas` | Baseline comparison in benchmark only |

### Explicitly Excluded

- `langchain`, `llama-index` — no framework dependency in ingest layer; SIRA owns that boundary.
- `pycylon` — deferred to v0.2 distributed track.
- `ray` — out of scope for v0.1 single-machine target.

---

*End of spec. Next: engineering kickoff → OQ-1 and OQ-2 resolution → sprint planning.*
