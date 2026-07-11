# Repository Guidelines

## Project Structure & Module Organization

This repository targets TKMEM/EvolveMem from arXiv `2605.13941` through a TicketMind support-ticket retrieval prototype. BM25/sketch retrieval is retained as a lexical baseline; EvolveMem-style retrieval evolution is the primary framing.

- `ticketmind-spec.md` — product and technical specification.
- `ticketmind-dashboard.html` — static admin/operations dashboard prototype.
- `elovemem-paper.txt` — arXiv `2605.13941` source reference notes.

When implementation files are added, keep the Python application under `sira/` with `src/` for modules, `tests/` for pytest coverage, `scripts/` for CLI utilities, and `data/` for local corpora and generated indexes. Do not commit generated artifacts such as BM25 pickles, `df_store.json`, or enriched corpora unless explicitly required.

## Build, Test, and Development Commands

Run implementation commands from `sira/`, not the repository root.

```bash
python3 -m pytest tests/
python3 -m pytest tests/test_retrieve.py
python3 src/index.py data/kb_corpus.jsonl --output data/bm25_index.pkl
python3 scripts/query.py "app keeps crashing"
python3 scripts/query.py --evolved "My app keeps crashing on login"
uvicorn src.enrich_ui:app --reload
```

Use `python3`; `python` may not be available. LLM-backed enrichment and sketch generation require Ollama with `qwen2.5:14b`.

## Coding Style & Naming Conventions

Use clear, idiomatic Python with 4-space indentation, snake_case functions and variables, and PascalCase classes. Keep modules focused on the pipeline stage they implement, such as `index.py`, `sketch.py`, `df_filter.py`, and `retrieve.py`. Prefer deterministic helper functions for tokenization, filtering, and scoring so tests can mock LLM calls cleanly.

For the static dashboard, keep CSS and JavaScript organized by feature area and avoid unrelated visual rewrites when changing behavior.

## Testing Guidelines

Use `pytest`. Name files `test_*.py` and tests `test_<behavior>()`. Mock all Ollama/LLM calls; unit tests should not require network access or a running model. Retrieval tests should inject fixtures with `_set_index()` and reset global state between tests.

## Commit & Pull Request Guidelines

No commit history is available in this checkout. Use concise, imperative commit messages, for example `Add DF sketch validation tests` or `Fix enriched corpus idempotency`.

Pull requests should include a short summary, test commands run, any generated files intentionally excluded, and screenshots for dashboard changes. Link related issues or spec sections when the change implements a documented requirement.

## Security & Configuration Tips

Keep secrets and local service URLs out of commits. Use environment variables such as `OLLAMA_HOST` and `OLLAMA_MODEL` for LLM configuration. Rebuild the BM25 index after corpus changes because the pickle stores the full `CorpusIndex`.
