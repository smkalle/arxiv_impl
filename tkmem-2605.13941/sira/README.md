# TicketMind/TKMEM Implementation

This directory contains the runnable implementation increments for arXiv `2605.13941`: TKMEM/EvolveMem-style retrieval evolution for LLM-agent memory. BM25 and sketch components are local lexical baselines so the prototype remains runnable without SimpleMem/LanceDB installed.

## Iteration 1 Commands

Run all commands from this `sira/` directory.

```bash
pip install -r requirements.txt
python3 src/index.py data/kb_corpus.jsonl --output data/bm25_index.pkl
python3 scripts/query.py "app keeps crashing"
python3 -m pytest tests/
```

The index command writes `data/bm25_index.pkl` and `data/df_store.json`. These are generated artifacts and can be rebuilt from `data/kb_corpus.jsonl`.

## Iteration 2 Enrichment

Offline enrichment adds customer-language search terms to each KB article:

```bash
python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
python3 src/enrich.py --input data/enriched_corpus.jsonl --output data/enriched_corpus_2.jsonl
python3 src/index.py data/enriched_corpus.jsonl --output data/bm25_index.pkl
```

The enrichment backend uses `OLLAMA_HOST` and `OLLAMA_MODEL`. Defaults are `http://localhost:11434` and `qwen2.5:14b`; bare hosts such as `127.0.0.1:11434` are normalized. If Ollama is unavailable, the CLI uses a deterministic local fallback so development signoff can still produce inspectable `enriched_terms`.

Generated enriched corpora are ignored by git and can be rebuilt from `data/kb_corpus.jsonl`.

## App Management

Use the management script for common local workflows:

```bash
scripts/manage.sh build
scripts/manage.sh eval
scripts/manage.sh start
scripts/manage.sh smoke
scripts/manage.sh stop
scripts/manage.sh status
```

Run `scripts/manage.sh help` for all subcommands. Background API and dashboard logs are written under `logs/`; PID files are written under `data/run/`.

## Baseline Query Examples

```bash
python3 scripts/query.py "app keeps crashing"
python3 scripts/query.py "subscription keeps renewing"
python3 scripts/query.py "password email never arrives"
```
