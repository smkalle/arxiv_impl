# sira-kb-ingestor

`sira-kb-ingestor` combines AAFLOW ticket ingestion with SIRA KB enrichment and retrieval. The package builds ticket embeddings, enriches KB articles through Ollama, builds a BM25 KB index, and exposes a CLI plus FastAPI retrieval server.

## Install

From this directory:

```bash
python3 -m pip install --upgrade pip setuptools wheel
python3 -m pip install -e ".[dev]"
```

Runtime enrichment and sketch generation use Ollama. For low-memory machines or sandboxes where the default Ollama model path is not writable, start Ollama with the project-local model store:

```bash
scripts/start_local_ollama.sh
```

In another shell:

```bash
export OLLAMA_HOST=http://127.0.0.1:11435
ollama pull qwen2.5-coder:3b
```

Ticket embedding defaults to `deterministic-hash`, a local fixed hash-vector extractor intended for low-memory text log annotation. It does not require PyTorch or `sentence-transformers`.

If you already run Ollama elsewhere, set `OLLAMA_HOST` to that endpoint instead.

## Configuration

Configuration precedence is `CLI > file > env > defaults`.

Local file discovery checks `./.sira-ingest.toml`, then `~/.config/sira-ingest/config.toml`.

```toml
[ingest]
batch_size = 128
max_workers = 4
embed_model = "deterministic-hash"

[enrichment]
enrichment_model = "qwen2.5-coder:3b"
ollama_host = "http://127.0.0.1:11435"

[retrieval]
top_k = 5
tau = 0.01
weight = 1.5

[output]
path = "./sira-artifacts"
```

Supported env vars include `SIRA_INGEST_BATCH_SIZE`, `SIRA_INGEST_MAX_WORKERS`, `SIRA_INGEST_EMBED_MODEL`, `SIRA_INGEST_ENRICHMENT_MODEL`, `SIRA_INGEST_TAU`, `SIRA_INGEST_WEIGHT`, `SIRA_INGEST_TOP_K`, and `SIRA_INGEST_OLLAMA_HOST`.

## Artifact Contract

`sira-ingest setup` writes the following files under `--out`:

```text
tickets.arrow
ticket_index.faiss
enriched_kb.jsonl
kb_index.pkl
setup_summary.json
```

`setup_summary.json` records ticket rows ingested, KB articles enriched, elapsed seconds, embedding metadata, and retrieval defaults.

## CLI

Build artifacts from Zendesk CSV tickets and SIRA KB JSONL:

```bash
sira-ingest setup \
  --tickets ./tickets.csv \
  --kb ./kb_corpus.jsonl \
  --out ./sira-artifacts \
  --batch-size 128 \
  --max-workers 4 \
  --embed-model deterministic-hash \
  --enrichment-model qwen2.5-coder:3b
```

Query built artifacts:

```bash
sira-ingest query --text "customer cannot sign in" --out ./sira-artifacts --top-k 5
```

Run the API server:

```bash
sira-ingest server --out ./sira-artifacts --host 0.0.0.0 --port 8000 --workers 4
```

Measure setup throughput:

```bash
sira-ingest benchmark \
  --tickets ./tickets.csv \
  --kb ./kb_corpus.jsonl \
  --rows 1000,5000,10000 \
  --runs 3 \
  --out ./sira-artifacts/benchmarks
```

The benchmark command writes `benchmark_report.json` and `benchmark_table.md`, and prints the Markdown table to stdout.

## API

Start the server, then call:

```bash
curl -s http://localhost:8000/health
```

```bash
curl -s http://localhost:8000/retrieve \
  -H 'content-type: application/json' \
  -d '{"ticket_text":"customer cannot sign in","top_k":5,"tau":0.01,"weight":1.5}'
```

The retrieval response contains `kb_articles` and `audit`.

## Validation

```bash
python3 -m pytest -q
OLLAMA_HOST=http://127.0.0.1:11435 bash scripts/validate_iteration_4.sh
OLLAMA_HOST=http://127.0.0.1:11435 bash scripts/validate_all_completed_iterations.sh
```

Real integration tests use the deterministic ticket extractor by default and skip with a clear reason when Ollama, the configured model, or required runtime packages are unavailable.

## GitHub Notes

The repository intentionally ignores local model and runtime output directories:

```text
.ollama-models/
sira-artifacts/
artifacts/iteration_4/benchmark_smoke/
```

The committed validation artifacts are concise text summaries under `artifacts/iteration_*`; they are useful for release review but are not required at runtime.
