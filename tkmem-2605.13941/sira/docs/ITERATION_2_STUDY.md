# Iteration 2 Study: Offline KB Enrichment

## Scope

Iteration 2 adds batch enrichment for KB articles. It does not add online sketch generation, DF validation, weighted TKMEM evolved retrieval, API endpoints, or dashboard behavior.

## Requirements Trace

- Read `data/kb_corpus.jsonl` and write `data/enriched_corpus.jsonl`.
- Preserve each original article field.
- Add `enriched_terms`, `enriched_body`, `enriched_at`, and `last_updated`.
- Use `OLLAMA_HOST` and `OLLAMA_MODEL`, defaulting to `http://localhost:11434` and `qwen2.5:14b`.
- Parse common LLM term formats and reject original-text duplicates, mixed alphanumerics, suspicious long single tokens, and duplicates.
- Skip articles where `enriched_at >= last_updated`.

## Design Notes

`src/enrich.py` owns the offline batch flow. Ollama remains the primary backend, while a deterministic local fallback is used when the backend is unavailable so developer signoff can still create inspectable enriched corpora. Fallback-enriched articles are marked with `enrichment_backend: heuristic-fallback`; Ollama articles are marked `enrichment_backend: ollama`.

`enriched_body` appends `Customer language: ...` to the original body. This is compatible with `CorpusIndex`, which already indexes `enriched_body` when present and includes `enriched_terms` in document-frequency counts.

## Completion Evidence

The following commands were run from `sira/`:

```bash
python3 -m pytest tests/
python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
python3 src/enrich.py --input data/enriched_corpus.jsonl --output data/enriched_corpus_2.jsonl
python3 src/index.py data/enriched_corpus.jsonl --output data/bm25_index.pkl
python3 -m compileall src scripts
python3 scripts/query.py "app keeps crashing"
python3 scripts/query.py "subscription keeps renewing"
python3 scripts/query.py "password email never arrives"
```

Observed results:

- `pytest` collected 14 tests and all 14 passed.
- Enrichment processed 10 articles, enriched 10, skipped 0, failed 0.
- Idempotency rerun processed 10 articles, enriched 0, skipped 10, failed 0.
- Enriched corpus term counts were 10-11 terms per article.
- Rebuilt enriched index printed `indexed_articles=10`.
- Smoke queries returned `KB-1001`, `KB-1003`, and `KB-1002` first for the three documented examples.
