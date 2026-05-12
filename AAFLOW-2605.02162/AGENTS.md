# AGENTS.md — kb-ingestor (AAFLOW-2605.02162)

## Status

Core scaffolding is in place (iterations 0-10 complete). Continue implementation from spec and `CLAUDE.md` using the iteration checklist below.

Primary sources of truth (read these before writing any code):
- `CLAUDE.md` — architecture summary, error classes, open questions
- `AAFLOW-arXiv:2605.02162-spec-kb-ingestor.md` — full product spec (canonical)
- `paper-summary.txt` / `2605.02162v1.pdf` — upstream AAFLOW paper

---

## What to build

`kb-ingestor v0.1.0`: a zero-copy Arrow-native pipeline that ingests Zendesk CSV / Jira JSON ticket exports into a FAISS vector index. Feeds the SIRA retrieval system in `../sira/`.

**Core constraint:** `pa.Table` must be the data type at every operator boundary. No `df.to_list()`, no intermediate numpy casts between operators. Violations of this break the zero-copy guarantee the whole project is built around.

---

## Implementation plan

Build in this order — each phase has a hard dependency on the previous:

### Phase 1 — Package scaffold
- Create `kb_ingestor/` package with `__init__.py` exporting `ingest`, `IngestConfig`, `IngestResult`
- Create `pyproject.toml` (or `setup.py`) with runtime deps: `pyarrow≥15`, `faiss-cpu≥1.8`, `sentence-transformers≥3`, `numpy≥1.26`, `click≥8`, `rich≥13`
- `tomllib` is stdlib in Python 3.11+ — no extra dep needed
- Dev deps: `pytest`, `pytest-asyncio`, `faker`, `pandas` (benchmark baseline only — never import pandas in `kb_ingestor/`)

### Phase 2 — Data model & error classes
- Define all 6 error classes in `kb_ingestor/errors.py`: `IngestSchemaError`, `IngestNullError`, `EmbedModelError`, `EmbedDimMismatchError`, `FAISSWriteError`, `BatchProcessingError`
- Define `IngestConfig` dataclass and `IngestResult` dataclass in `kb_ingestor/models.py`
- Canonical 7-column Arrow schema (see spec §5.3) — define as a module-level `pa.schema()` constant

### Phase 3 — Operators (implement in pipeline order)

**OP-1 `kb_ingestor/ops/load.py`**
- `load(source: Path | pa.Table, config: IngestConfig) -> pa.Table`
- CSV: use `pa.csv.read_csv()` with `ConvertOptions` — never `pd.read_csv`
- JSON: use `pa.json.read_json()` then extract nested Jira fields (`fields.summary`, `fields.description`, etc.)
- Source type auto-detected from file extension; override via `config.source_type`
- Missing required columns → `IngestSchemaError` listing them
- Null `description` rows: drop (default) or raise `IngestNullError` per `config.null_policy`

**OP-2 `kb_ingestor/ops/chunk.py`**
- `chunk(table: pa.Table, config: IngestConfig) -> pa.Table`
- `text_input = subject + " " + description` via `pc.binary_join_element_wise`
- Slice with `pc.utf8_slice_codeunits(text_input, 0, config.max_chunk_chars)` — no Python loop
- v0.1: single chunk per ticket; `chunk_index` column is all zeros
- Drop chunks shorter than `config.min_chunk_chars` (default 20)

**OP-3 `kb_ingestor/ops/embed.py`**
- `async embed(table: pa.Table, config: IngestConfig) -> pa.Table`
- Split table into `config.batch_size` sub-tables
- Each batch: extract chunk column as numpy, call `embedder.encode()` in thread via `asyncio.to_thread`
- Dispatch all batches concurrently with `asyncio.gather` + `asyncio.Semaphore(config.max_workers)`
- Cast result to `pa.list_(pa.float32())`, merge all batches with `pa.concat_tables`
- Model dim mismatch on append → `EmbedDimMismatchError`

**OP-4 `kb_ingestor/ops/upsert.py`**
- `upsert(table: pa.Table, index: faiss.Index) -> tuple[pa.Table, faiss.Index]`
- Extract embeddings: `np.array(table["embedding"].to_pylist(), dtype=np.float32)`
- `index.add(embeddings)` — sequential only; `IndexFlatL2` is not thread-safe for `add`
- `faiss_id` = contiguous integers from `index.ntotal` before add; stored as `pa.int64()`
- Write to temp dir then `os.replace()` for atomic output (disk full → `FAISSWriteError`)

### Phase 4 — Public API & CLI
- `kb_ingestor/api.py`: `async ingest(source, config) -> IngestResult` — chains OP-1 → OP-4
- Output artifacts: `tickets.arrow` (Arrow IPC, LZ4 uncompressed), `index.faiss`, `run_summary.json` with `embed_dim` key
- `kb_ingestor/cli.py`: `click` group with subcommands `run`, `benchmark`, `validate`
- Config file: `.kb-ingestor.toml` in CWD first, then `~/.config/kb-ingestor/config.toml`; CLI flags override

### Phase 5 — Test fixtures & tests
- `make fixtures` script generates `fixtures/zendesk_1k.csv` and `fixtures/jira_1k.json` using `faker` — no real ticket data
- Fixtures must include 5% null descriptions and UTF-8 edge cases (Japanese, Arabic)
- Tests in `tests/` — all use `pytest-asyncio` for async operator tests
- Unit tests: see spec §11.1 — 10 named test functions
- Integration tests: see spec §11.2 — 5 named test functions
- Performance gate: `kb-ingest benchmark --rows 1000 --runs 1` must show speedup ≥2.0× vs pandas baseline

### Phase 6 — Benchmark subcommand
- `kb-ingest benchmark --source PATH --rows 1000,5000,10000 --runs 3`
- Run 3× at each scale; report mean ± std
- Baseline = `pd.read_csv → .tolist() → encode → faiss.add`
- Output: Markdown table to stdout + `benchmark_results.json` to `--out` dir
- CI gate: speedup < 2.0× fails the build

---

## Critical constraints (will break correctness if violated)

- **Never use pandas in `kb_ingestor/` production code.** Pandas is allowed only in the benchmark baseline path.
- **Never import `langchain`, `llama-index`, `pycylon`, or `ray`.** These are explicitly excluded.
- **`faiss_id` must be contiguous integers matching FAISS row positions.** This is the join key SIRA uses to map search results back to the Arrow table. Any gap corrupts retrieval.
- **OP-4 (`index.add`) must be sequential.** `IndexFlatL2` is not thread-safe for writes.
- **Arrow IPC output must be uncompressed LZ4** (default) so SIRA can mmap it directly. Don't set `compress=True` unless the user explicitly requests it.
- **`run_summary.json` must include `embed_dim`** — SIRA uses this key for model discovery.
- **`tomllib` is Python 3.11+ stdlib.** Do not add it as a pip dependency; add a `sys.version_info` guard if supporting <3.11.

---

## Unresolved before v0.1 cut (get answers before implementing affected code)

- **OQ-1**: v0.1 truncates at 512 chars. Multi-chunk sliding window is deferred to v0.2 — do not implement now.
- **OQ-2**: Embedding model alignment with SIRA's BM25+LLM enrichment approach. Default to `all-MiniLM-L6-v2` (384-dim) until resolved.

---

## Key defaults

| Parameter | Default |
|---|---|
| `batch_size` | 128 |
| `max_workers` | 4 |
| `embed_model` | `all-MiniLM-L6-v2` |
| `max_chunk_chars` | 512 |
| `min_chunk_chars` | 20 |
| `null_policy` | `"drop"` |
| `faiss_factory` | `"Flat"` (IndexFlatL2) |

## Environment variables

| Variable | Default |
|---|---|
| `KB_INGESTOR_EMBED_MODEL` | `all-MiniLM-L6-v2` |
| `KB_INGESTOR_MAX_WORKERS` | `4` |
| `KB_INGESTOR_LOG_LEVEL` | `INFO` |
| `TRANSFORMERS_CACHE` | HuggingFace default |

---

## Iteration checklist (publish before build)

Use this as the execution checklist. Each iteration requires design, plan, implementation, tests, and explicit signoff artifacts that a human can inspect.

Human validation is mandatory per iteration:
- Include release notes: `RELEASE_NOTES_ITERATION_<N>.md`
- Include a runnable validation script: `scripts/validate_iteration_<N>.sh`
- Include one visible user-facing change artifact. For this mostly non-UI project, a CLI-visible artifact is acceptable (e.g., saved `--help` output, benchmark Markdown table, or command transcript).
- Update the Streamlit human-validation UI (`scripts/human_validation_ui.py`) to include the current iteration artifacts and checks.
- Update `scripts/validate_all_completed_iterations.sh` so it runs all completed iteration validators.

### Iteration 0 — Kickoff and contract freeze
- [x] **Design:** freeze v0.1 scope (single-chunk truncation, batch-only, IndexFlatL2, zero-copy Arrow data plane)
- [x] **Plan:** produce requirement→test mapping from spec §5–§11
- [x] **Implementation:** create planning docs only (no runtime code)
- [x] **Test:** review docs against `CLAUDE.md` + product spec
- [x] **Signoff artifacts:** `IMPLEMENTATION_PLAN.md`, `ACCEPTANCE_MATRIX.md`
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_0.md`
- [x] **Validation script:** `scripts/validate_iteration_0.sh`
- [x] **Visible change artifact:** `artifacts/iteration_0/validation_output.txt`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 0 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 0

### Iteration 1 — Scaffold
- [x] **Design:** package/module layout and public API surface
- [x] **Plan:** dependency split (runtime vs dev), CLI/config precedence
- [x] **Implementation:** `pyproject.toml`, `kb_ingestor/__init__.py`, CLI skeleton (`run|benchmark|validate`)
- [x] **Test:** import smoke tests + CLI help smoke test
- [x] **Signoff artifacts:** `pyproject.toml`, `kb_ingestor/__init__.py`, `kb-ingest --help` output log
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_1.md`
- [x] **Validation script:** `scripts/validate_iteration_1.sh`
- [x] **Visible change artifact:** CLI help transcript in `artifacts/iteration_1/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 1 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 1

### Iteration 2 — Models and errors
- [x] **Design:** canonical 7-column schema, dataclass defaults, error message shape
- [x] **Plan:** define validation boundaries for when each error is raised
- [x] **Implementation:** `kb_ingestor/models.py`, `kb_ingestor/errors.py`
- [x] **Test:** unit tests for schema/types/defaults and error constructors
- [x] **Signoff artifacts:** model/error files + test log for schema assertion
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_2.md`
- [x] **Validation script:** `scripts/validate_iteration_2.sh`
- [x] **Visible change artifact:** saved test transcript in `artifacts/iteration_2/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 2 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 2

### Iteration 3 — OP-1 load/normalize
- [x] **Design:** CSV/JSON source detection and Jira nested extraction rules
- [x] **Plan:** null policy behavior (`drop` vs `raise`) and required-column checks
- [x] **Implementation:** `kb_ingestor/ops/load.py` using `pa.csv.read_csv` / `pa.json.read_json` (no pandas)
- [x] **Test:** `test_load_zendesk_csv`, `test_load_jira_json`, `test_load_arrow_table`, null-policy tests
- [x] **Signoff artifacts:** normalized table sample print + error-path logs for schema/null failures
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_3.md`
- [x] **Validation script:** `scripts/validate_iteration_3.sh`
- [x] **Visible change artifact:** sample normalized output log in `artifacts/iteration_3/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 3 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 3

### Iteration 4 — OP-2 chunk/preprocess
- [x] **Design:** chunk composition, truncation, min-length filter, UTF-8 handling
- [x] **Plan:** ensure vectorized Arrow compute only (no row loops)
- [x] **Implementation:** `kb_ingestor/ops/chunk.py` with `pc.binary_join_element_wise` + `pc.utf8_slice_codeunits`
- [x] **Test:** `test_chunk_vectorized` (length, UTF-8 edges, `chunk_index==0`)
- [x] **Signoff artifacts:** chunk output sample and passing test log
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_4.md`
- [x] **Validation script:** `scripts/validate_iteration_4.sh`
- [x] **Visible change artifact:** chunk sample transcript in `artifacts/iteration_4/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 4 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 4

### Iteration 5 — OP-3 async embed
- [x] **Design:** async batch concurrency model (`asyncio.gather` + semaphore + to_thread)
- [x] **Plan:** batch failure aggregation and model load failure handling
- [x] **Implementation:** `kb_ingestor/ops/embed.py`, float32 Arrow list embedding column
- [x] **Test:** `test_embed_output_shape` + batch/error-path tests
- [x] **Signoff artifacts:** async batch timing log and embedding shape/dtype evidence
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_5.md`
- [x] **Validation script:** `scripts/validate_iteration_5.sh`
- [x] **Visible change artifact:** timing/test transcript in `artifacts/iteration_5/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 5 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 5

### Iteration 6 — OP-4 upsert
- [x] **Design:** append semantics, dim-compatibility checks, atomic write pattern
- [x] **Plan:** enforce sequential `index.add` and contiguous ID assignment
- [x] **Implementation:** `kb_ingestor/ops/upsert.py`, `faiss_id` from pre-add `index.ntotal`
- [x] **Test:** `test_faiss_id_contiguous`, `test_append_mode`, `test_dim_mismatch_raises`, write-failure path
- [x] **Signoff artifacts:** `faiss_id` vs FAISS row-position verification log
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_6.md`
- [x] **Validation script:** `scripts/validate_iteration_6.sh`
- [x] **Visible change artifact:** FAISS ID verification transcript in `artifacts/iteration_6/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 6 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 6

### Iteration 7 — Orchestration API and artifact writer
- [x] **Design:** OP chain contract and in-memory vs file-output behavior
- [x] **Plan:** artifact schema (`tickets.arrow`, `index.faiss`, `run_summary.json` with `embed_dim`)
- [x] **Implementation:** `kb_ingestor/api.py` async `ingest()` orchestration
- [x] **Test:** e2e API tests for CSV and JSON sources
- [x] **Signoff artifacts:** generated artifact trio in temp output and reload proof
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_7.md`
- [x] **Validation script:** `scripts/validate_iteration_7.sh`
- [x] **Visible change artifact:** artifact listing/reload transcript in `artifacts/iteration_7/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 7 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 7

### Iteration 8 — CLI completion
- [x] **Design:** UX, exit-code mapping, config file discovery order
- [x] **Plan:** command-specific validation behavior and error display
- [x] **Implementation:** complete `kb_ingestor/cli.py` command wiring
- [x] **Test:** CLI exit-code tests and command smoke tests
- [x] **Signoff artifacts:** captured command transcripts for `run`, `validate`, `benchmark`
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_8.md`
- [x] **Validation script:** `scripts/validate_iteration_8.sh`
- [x] **Visible change artifact:** CLI transcripts in `artifacts/iteration_8/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 8 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 8

### Iteration 9 — Fixtures and full integration
- [x] **Design:** fixture characteristics (1K rows, 5% null descriptions, UTF-8 edge cases)
- [x] **Plan:** deterministic fixture generation workflow (`make fixtures`)
- [x] **Implementation:** fixture generator + integration tests
- [x] **Test:** `test_e2e_zendesk_1k`, `test_e2e_jira_1k`, `test_sira_roundtrip`, `test_benchmark_output_format`
- [x] **Signoff artifacts:** fixture files + integration test logs
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_9.md`
- [x] **Validation script:** `scripts/validate_iteration_9.sh`
- [x] **Visible change artifact:** integration transcript in `artifacts/iteration_9/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 9 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 9

### Iteration 10 — Benchmark gate and release readiness
- [x] **Design:** benchmark protocol and pass/fail threshold policy
- [x] **Plan:** baseline path (`pandas` only in benchmark baseline branch)
- [x] **Implementation:** benchmark report generation (Markdown + JSON)
- [x] **Test:** `kb-ingest benchmark --rows 1000 --runs 1` gate and sanity runs at larger sizes
- [x] **Signoff artifacts:** benchmark table, `benchmark_results.json`, `RELEASE_v0.1.0.md`
- [x] **Release notes:** `RELEASE_NOTES_ITERATION_10.md`
- [x] **Validation script:** `scripts/validate_iteration_10.sh`
- [x] **Visible change artifact:** benchmark table snapshot in `artifacts/iteration_10/`
- [x] **UI update:** `scripts/human_validation_ui.py` shows iteration 10 artifacts/checks
- [x] **Aggregate validator update:** `scripts/validate_all_completed_iterations.sh` runs iteration 10

### Definition of done per iteration
- [ ] Design notes updated for decisions and constraints preserved
- [ ] Tests added for all new behavior and passing locally
- [ ] At least one human-verifiable artifact produced and saved
- [ ] Release notes written for the iteration and linked from PR/summary
- [ ] Validation script executes successfully and writes output under `artifacts/iteration_<N>/`
- [ ] One visible user-facing artifact captured (CLI-visible output accepted)
- [ ] Streamlit validation UI reflects the current iteration's release notes and artifacts
- [ ] `scripts/validate_all_completed_iterations.sh` includes the current iteration
- [ ] Zero-copy invariant preserved across operator boundaries
- [ ] No banned deps added to production path (`pandas`, `langchain`, `llama-index`, `pycylon`, `ray`)
