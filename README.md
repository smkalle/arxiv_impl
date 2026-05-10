# arxiv_impl

Implementations of arXiv papers.

## Active project

- `sira_arXiv:2605.06647/` — implementation of Meta's SIRA retrieval approach
  (training-free vocabulary bridging with LLM enrichment + weighted BM25).

## Current status (SIRA project)

- Iteration 1–4 implemented (Iteration 4 API is running, auth intentionally skipped).
- Iteration 5 (evaluation harness + ablation runner) pending.

## Quickstart

Run all commands from:

```bash
cd sira_arXiv:2605.06647
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Run tests:

```bash
python3 -m pytest tests/
```

Start services:

```bash
./scripts/start_api.sh
./scripts/start_ui.sh
```

- API docs: `http://localhost:8001/docs`
- Operations UI: `http://localhost:8000/`

## Notes for pushing to GitHub

- Generated artifacts (index pickle, df store, enriched corpora, feedback logs, local PID/log files)
  are ignored via `.gitignore`.
- Keep `data/kb_corpus.jsonl` tracked as the seed dataset.
