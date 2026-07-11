# SIRA KB ingestor

`sira-kb-ingestor/` is the packaged bridge between ticket ingestion and SIRA-style retrieval. It combines AAFLOW-like ticket artifact generation with KB enrichment and retrieval so one CLI can build the end-to-end artifact set needed by downstream consumers.

## What it produces

The project's artifact contract is explicit:

- `tickets.arrow`
- `ticket_index.faiss`
- `enriched_kb.jsonl`
- `kb_index.pkl`
- `setup_summary.json`

`setup_summary.json` records counts, elapsed time, embedding metadata, and retrieval defaults. The package README emphasizes that these outputs are the primary interface, not internal Python objects.

## Major workflows

### 1. Setup

The `setup` command orchestrates the full pipeline:

1. ingest tickets,
2. enrich the KB,
3. build the KB BM25 index,
4. write summary metadata.

The orchestration code handles input validation, artifact directory creation, and copy-through of upstream AAFLOW artifacts into the local output directory.

### 2. Query

The `query` command loads an artifact directory and runs retrieval against the built KB index.

### 3. Server

The `server` command exposes the retrieval API for the built artifacts.

### 4. Benchmark

The `benchmark` command measures setup throughput over multiple row counts and writes both a JSON report and a Markdown table.

## Configuration precedence

Configuration is resolved in this order:

1. CLI flags
2. config file
3. environment variables
4. defaults

Config discovery checks:

- `./.sira-ingest.toml`
- `~/.config/sira-ingest/config.toml`

The parser is intentionally small and only supports the local v0.1 needs described in `config.py`.

## Runtime composition

Important implementation details from `orchestration.py`:

- The setup flow dynamically imports AAFLOW and SIRA code by adding both repositories to `sys.path`.
- If `embed_model == "deterministic-hash"`, it uses a local deterministic ingest path.
- Otherwise, it calls the AAFLOW package's ingest API.
- KB enrichment is delegated to `src.enrich.enrich_corpus` from the SIRA workspace.
- The KB index is built with `src.index.build_and_save` from SIRA.

That means this package is a real integration layer, not a copy of either upstream project.

## Dependency and compatibility notes

`pyproject.toml` shows the runtime surface is intentionally compact: `pyarrow`, `faiss-cpu`, `numpy`, `click`, `rich`, `fastapi`, and `uvicorn`. The dev extras only add test-time helpers.

One subtle compatibility issue to watch: the orchestration code imports from both `sira_kb_ingestor` and the external `kb_ingestor` / `src` modules after amending `sys.path`. If you change package layout or rename modules in either upstream workspace, this bridge may need to change too.

## Validation and testing

The integration tests build both Zendesk CSV and Jira JSON scenarios, then verify that the output artifacts exist and that retrieval returns the expected response shape.

The package README also documents:

- local Ollama startup via `scripts/start_local_ollama.sh`,
- `sira-ingest setup`, `query`, `server`, and `benchmark` usage,
- a `python3 -m pytest -q` validation path,
- iteration validation shell scripts.

## Watchouts for future changes

- Keep artifact names stable unless you update the downstream consumers at the same time.
- Respect the config precedence order; tests likely depend on it.
- If you change the deterministic ingest path, verify the orchestration fallback behavior still works without a model server.
- If you change the retrieval response shape, update the integration tests and the README examples.

## Source references

- `/sira-kb-ingestor/README.md`
- `/sira-kb-ingestor/pyproject.toml`
- `/sira-kb-ingestor/sira_kb_ingestor/cli.py`
- `/sira-kb-ingestor/sira_kb_ingestor/config.py`
- `/sira-kb-ingestor/sira_kb_ingestor/orchestration.py`
- `/sira-kb-ingestor/sira_kb_ingestor/api.py`
- `/sira-kb-ingestor/tests/test_integration.py`
