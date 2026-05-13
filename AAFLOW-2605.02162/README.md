# kb-ingestor (AAFLOW-2605.02162)

`kb-ingestor` is a zero-copy Arrow-native pipeline that ingests Zendesk CSV and Jira JSON ticket exports into a FAISS vector index.

This project implements a productized ingest path derived from the AAFLOW paper (`arXiv:2605.02162`) and is designed to feed retrieval systems such as SIRA.

> **Admin Dashboard** — a purpose-built ops and admin console for this pipeline ships in [`dashboard/`](dashboard/). Start it with `bash dashboard/start.sh` and open `http://localhost:8000`.

## Key guarantees

- Operator boundaries use `pyarrow.Table` throughout.
- Output artifacts are:
  - `tickets.arrow`
  - `index.faiss`
  - `run_summary.json` (includes mandatory `embed_dim`)
- `faiss_id` is contiguous and aligned with FAISS row positions.

## Install

From this directory:

```bash
python3 -m pip install -e .
```

For dev/test extras:

```bash
python3 -m pip install -e .[dev]
```

## CLI quickstart

Run ingest:

```bash
python3 -m kb_ingestor.cli run --source fixtures/zendesk_1k.csv --out ./kb_output
```

Validate source schema:

```bash
python3 -m kb_ingestor.cli validate --source fixtures/zendesk_1k.csv
```

Benchmark:

```bash
python3 -m kb_ingestor.cli benchmark --source fixtures/zendesk_1k.csv --rows 1000 --runs 1 --out ./benchmark_output
```

## Python API

```python
from pathlib import Path
from kb_ingestor import ingest, IngestConfig

result = await ingest(Path("fixtures/zendesk_1k.csv"), IngestConfig(output_path=Path("./kb_output")))
```

## Operator pipeline

1. `load` -> normalize source to canonical ticket schema
2. `chunk` -> vectorized chunk generation/truncation
3. `embed` -> async batched embedding append
4. `upsert` -> sequential FAISS add + contiguous `faiss_id`

## Human validation workflow

- Run one iteration validator:

```bash
bash scripts/validate_iteration_7.sh
```

- Run all completed iterations:

```bash
bash scripts/validate_all_completed_iterations.sh
```

- Launch Streamlit human validation UI:

```bash
scripts/human_validation_ui.sh
```

## Notes

- Fixtures are synthetic (generated); no real ticket data is included.
- Current implementation is single-machine, batch-oriented v0.1.0 scope.
