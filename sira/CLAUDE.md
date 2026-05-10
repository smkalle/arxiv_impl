# CLAUDE.md

Repository guidance for coding agents working in this project.

## Project status

This repository is implemented code (not spec-only).

- Iteration 1–3: implemented and tested.
- Iteration 4: implemented (`src/api.py`, `src/models.py`, `tests/test_api.py`), auth intentionally skipped.
- Iteration 5: pending (`src/eval.py`, `scripts/run_ablations.py`, annotated test set).

## Run location

Run all commands from:

```bash
cd sira_arXiv:2605.06647
```

## Core commands

```bash
# tests
python3 -m pytest tests/

# build index (preferred via import path to avoid pickle module-name issues)
PYTHONPATH=. python3 -c "from src.index import build_and_save; build_and_save('data/enriched_corpus.jsonl','data/bm25_index.pkl')"

# enrichment batch
PYTHONPATH=. python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl

# API and UI services
./scripts/start_api.sh
./scripts/start_ui.sh
```

## Model/runtime notes

- Enrichment/query model control is exposed in `src/enrich_ui.py` via `/api/models*` endpoints.
- UI allowlist excludes `qwen3:4b`; selectable models are explicitly controlled in backend allowlist.
- UI model state tracks enrich/sketch models independently and attempts old-model unload via Ollama to reduce memory pressure.

## Artifacts and git hygiene

- Generated files in `data/` (index pickle, df store, enriched outputs, feedback logs) are not meant for commit.
- Local runtime files (`.api_server.*`, `.ui_server.*`) are ignored.
