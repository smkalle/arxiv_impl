# Release v0.1.0

## Feature Checklist

- [x] Package metadata and `sira-ingest` console script
- [x] Config discovery and precedence: CLI, file, env, defaults
- [x] `sira-ingest setup` for ticket ingest, KB enrichment, BM25 index build, and summary output
- [x] `sira-ingest query` JSON retrieval output with non-zero failure behavior
- [x] `sira-ingest server` FastAPI runner with spec defaults
- [x] `sira-ingest benchmark` setup-throughput reporting
- [x] Low-memory deterministic ticket extractor default: `deterministic-hash`
- [x] Artifact contract: `tickets.arrow`, `ticket_index.faiss`, `enriched_kb.jsonl`, `kb_index.pkl`, `setup_summary.json`
- [x] Iteration 4 validation script and aggregate validator update

## Validation Checklist

Run from this directory:

```bash
python3 -m pytest -q
OLLAMA_HOST=http://127.0.0.1:11435 bash scripts/validate_iteration_4.sh
OLLAMA_HOST=http://127.0.0.1:11435 bash scripts/validate_all_completed_iterations.sh
```

Expected iteration 4 artifacts:

```text
artifacts/iteration_4/validation_output.txt
artifacts/iteration_4/pytest_output.txt
artifacts/iteration_4/benchmark_table.md
```

## Required External Services

- Ollama reachable at `OLLAMA_HOST`; `scripts/start_local_ollama.sh` starts a project-local server at `http://127.0.0.1:11435`
- Ollama model `OLLAMA_MODEL`, default `qwen2.5-coder:3b`
- Python runtime dependencies from `pyproject.toml`
- Local access to the sibling AAFLOW and SIRA source trees used by orchestration imports

## Known Limits

- No hard benchmark performance gate is enforced in v0.1.0.
- Real integration tests skip when Ollama or the configured model is unavailable.
- The default ticket extractor is deterministic and lightweight; neural ticket embeddings require a custom ingest path or non-default embedding setup.
- The server runner passes an app object to Uvicorn; the CLI default is `--workers 4` to match the spec.
- KB enrichment depends on SIRA's Ollama-backed enrichment behavior unless articles are already current and skipped.
- The package is intended for script-style local operation; CI and wheel publication are not configured here.

## Sign-Off Steps

1. Install dev dependencies with `python3 -m pip install --upgrade pip setuptools wheel && python3 -m pip install -e ".[dev]"`.
2. Start Ollama with `scripts/start_local_ollama.sh` or point `OLLAMA_HOST` at an existing service.
3. Run `python3 -m pytest -q`.
4. Run `OLLAMA_HOST=http://127.0.0.1:11435 bash scripts/validate_iteration_4.sh`.
5. Run `OLLAMA_HOST=http://127.0.0.1:11435 bash scripts/validate_all_completed_iterations.sh`.
6. Review `artifacts/iteration_4/benchmark_table.md` and `artifacts/iteration_4/validation_output.txt`.
