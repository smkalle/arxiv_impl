# Final Signoff

Target paper: arXiv `2605.13941` / TKMEM-EvolveMem. BM25/sketch retrieval is treated as a runnable lexical baseline and local approximation where optional SimpleMem/LanceDB dependencies are unavailable.

## Verified Commands

Run from `sira/`.

```bash
python3 -m pytest tests/
python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
python3 src/index.py data/enriched_corpus.jsonl --output data/bm25_index.pkl
python3 src/evaluate.py --test-set data/annotated_test_set.jsonl --index data/bm25_index.pkl --report data/eval_report.json
python3 scripts/query.py --evolved "subscription keeps renewing" --tau 0.01 --weight 1.5
python3 -m compileall src scripts
python3 scripts/ops_status.py
```

Observed results:

- Unit tests: 25 passed.
- Enrichment: 10 processed, 10 enriched, 0 failed.
- Index build: 10 indexed articles.
- Evaluation: baseline F1@5 1.000, evolved F1@5 1.000, evolved P95 latency 532.71 ms.
- Compatibility evolution: mode `compatibility`, post-evolution F1@5 0.705, relative gain 0.175.

## UI/API Verification

Servers started successfully:

```bash
python3 -m uvicorn src.ticket_api:app --host 127.0.0.1 --port 8001
python3 -m uvicorn src.enrich_ui:app --host 127.0.0.1 --port 8000
```

Verified HTTP checks:

- `GET /health` returned `status=ok` and config version `local-v1`.
- `POST /query` returned top-k results, latency, fallback flag, and trace.
- Dashboard `/` rendered Query Inspector.
- Dashboard `/query/trace` rendered KB results and accepted/rejected sketch terms.
- Dashboard `/kb` rendered 10 KB rows with enrichment counts.
- Dashboard `/evolution` rendered 7 compatibility evolution rounds.
- Dashboard `/system` rendered index/corpus/dependency status.

Playwright/browser console verification was not run because Playwright is not installed. UI verification used HTTP-rendered page checks.

## Compatibility Notes

SimpleMem and LanceDB are not installed in this environment. Iteration 8 is implemented as a deterministic compatibility mode that reports dependency status and writes `data/evolution_state.json` plus `data/evolved_config.json`.
