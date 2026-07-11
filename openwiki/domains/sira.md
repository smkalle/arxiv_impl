# SIRA

SIRA in this repository is the implementation of Meta's arXiv paper `2605.06647`: a training-free retrieval pipeline that bridges support-ticket vocabulary to knowledge-base articles by combining offline LLM enrichment with online sketch expansion and weighted BM25 scoring.

## What the system does

The core retrieval path is intentionally lexical rather than embedding-based:

1. KB articles are enriched offline with customer-language search terms.
2. A live ticket query is transformed into a sketch of KB-style terms.
3. The sketch terms are filtered by document-frequency heuristics.
4. The final ranking combines original query BM25 scores with a weighted BM25 pass over validated sketch terms.

The current implementation falls back to plain BM25 if sketch generation fails or returns nothing.

## Important runtime pieces

From `sira/src/`:

- `index.py` — builds and stores the BM25 index, tokenizes text, and persists the DF counter.
- `enrich.py` — offline KB enrichment using Ollama.
- `sketch.py` — online sketch generation for queries.
- `df_filter.py` — validates sketch terms using the document-frequency threshold `tau`.
- `retrieve.py` — combines original query BM25 and sketch BM25 into the final retrieval response.
- `api.py` — retrieval API.
- `enrich_ui.py` — the enrichment monitor UI, distinct from the retrieval API.

## Data and scoring behavior that matters

A few implementation details are especially important for future edits:

- `CorpusIndex.load_corpus()` prefers `enriched_body` over `body` when both exist.
- The BM25 index is persisted as a pickle of the full `CorpusIndex` object.
- `build_and_save()` also writes a `df_store.json` next to the pickle by default.
- The DF counter folds in `enriched_terms` from each article as separate searchable terms.
- `sira_retrieve()` computes `final_score = BM25(original tokens) + w × BM25(validated sketch tokens)`.
- If sketch generation fails, times out, or yields no terms, the code records `fallback_used=True` and returns plain BM25 results.

## Enrichment rules

The enrichment path is built around a strict parsing and idempotency contract:

- The Ollama model defaults to `qwen2.5:3b` unless `OLLAMA_MODEL` is set.
- `enrich.py` uses `OLLAMA_HOST` with a localhost default.
- `_parse_terms()` removes terms that already appear in the article text, mixed alphanumeric terms, and long concatenated single tokens.
- `enrich_corpus()` skips articles where `enriched_at >= last_updated`, which means both timestamps must exist in the JSONL input for the idempotency check to work.

## Commands and operational entrypoints

From `sira/`:

```bash
python3 -m pytest tests/
PYTHONPATH=. python3 -c "from src.index import build_and_save; build_and_save('data/enriched_corpus.jsonl','data/bm25_index.pkl')"
PYTHONPATH=. python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
python3 scripts/query.py "app keeps crashing"
python3 scripts/query.py --sira "My app keeps crashing on login"
```

The local guidance also references `./scripts/start_api.sh` and `./scripts/start_ui.sh` for the two FastAPI services.

## Testing notes

The tests are designed to avoid real LLM calls by mocking the Ollama functions. Important test facts from the current codebase:

- The suite covers API, DF filtering, enrichment, evaluation, index building, and retrieval.
- Retrieval tests patch `src.retrieve.generate_sketch` directly because `retrieve.py` imports the symbol into its own namespace.
- Fixture setup pads the article corpus so the DF threshold still allows simple terms to pass validation in tests.

## Watchouts for future changes

- Rebuild the index after corpus changes because the pickle stores the complete index object.
- Keep tokenization and enrichment parsing changes aligned with the tests; several behaviors are intentionally hard-coded.
- If you change the shape of enriched corpus records, check both the index builder and the retrieval audit output.
- If you change the Ollama defaults or environment variables, update both `AGENTS.md` and `CLAUDE.md` in this subproject.

## Source references

- `/sira/AGENTS.md`
- `/sira/CLAUDE.md`
- `/sira/src/index.py`
- `/sira/src/enrich.py`
- `/sira/src/retrieve.py`
- `/sira/src/api.py`
- `/sira/tests/test_retrieve.py`
