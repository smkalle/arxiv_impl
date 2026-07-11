# Iteration 1 Study: Corpus Index and Plain BM25 Retrieval

## Scope

Iteration 1 implements the lexical retrieval baseline that later TKMEM iterations will enrich and re-rank. It deliberately avoids LLM calls, sketch generation, FastAPI, and dashboard behavior. The deliverable is a reproducible local BM25 index plus a CLI query path that a human can inspect.

## Requirements Trace

Source requirements come from `ITERATIONS.md` and `ticketmind-spec.md`:

- Load a KB JSONL corpus with stable `id`, `title`, and `body` fields.
- Tokenize consistently: lowercase, minimum length 2, and at least one alphanumeric character.
- Build a BM25 index from the corpus.
- Persist the full `CorpusIndex` pickle at `data/bm25_index.pkl`.
- Persist document frequencies at `data/df_store.json`.
- Provide a CLI query command that returns top-k KB IDs, titles, scores, and snippets.
- Cover tokenization, index persistence, and ranking behavior with unit tests.

## Design Decisions

`src/index.py` owns corpus loading, validation, tokenization, BM25 construction, and persistence. Keeping those responsibilities together makes the pickle format explicit and keeps future enrichment behavior close to DF counting.

`CorpusIndex` stores article metadata, tokenized documents, a `Counter` of document frequencies, and the `BM25Okapi` instance. The pickle stores the whole object because later iterations expect `load_index()` to restore the retrieval-ready index without rebuilding.

The tokenizer prefers `nltk.word_tokenize` when local NLTK data is installed, but falls back to a regex tokenizer. This preserves the intended tokenizer path while keeping first-run local scripts usable when `punkt` is not present.

The DF counter is computed from unique terms per article. It already accepts future `enriched_terms` as one set per article so Iteration 2 and 3 can add enrichment without changing the DF store contract.

`src/retrieve.py` keeps the global `_index` pattern expected by later evolved retrieval tests. Production code calls `load_index()`. Tests can inject fixtures with `_set_index()`.

`scripts/query.py` is the human-facing smoke path. It auto-builds `data/bm25_index.pkl` from `data/kb_corpus.jsonl` if the pickle is missing, then prints ranked results with enough context for manual validation.

## Start Checklist Status

- [x] `data/kb_corpus.jsonl` exists with stable `id`, `title`, and `body` fields.
- [x] Tokenization rules are implemented in `src/index.py:tokenize()`.
- [x] Generated index path is `data/bm25_index.pkl`.
- [x] Generated DF store path is `data/df_store.json`.

## Signoff Plan

Run from `sira/`:

```bash
python3 src/index.py data/kb_corpus.jsonl --output data/bm25_index.pkl
python3 scripts/query.py "app keeps crashing"
python3 -m pytest tests/
```

Expected evidence:

- Index command prints `indexed_articles=6`.
- Query command ranks `KB-1001` highly for crash/login language.
- Tests pass for tokenization, persistence, DF output, and ranking.

## Human Validation Plan

Run these examples and inspect whether the top result is sensible:

```bash
python3 scripts/query.py "app keeps crashing"
python3 scripts/query.py "subscription keeps renewing"
python3 scripts/query.py "password email never arrives"
```

Expected behavior:

- Crash/login query should surface `KB-1001`.
- Subscription/renewal query should surface `KB-1003`.
- Password email query should surface `KB-1002`.

Also inspect `data/df_store.json`; common support terms should have integer document frequencies and generated artifacts should be reproducible from the corpus.

## Completion Evidence

The following commands were run from `sira/`:

```bash
python3 -m pytest tests/
python3 src/index.py data/kb_corpus.jsonl --output data/bm25_index.pkl
python3 -m compileall src scripts
python3 scripts/query.py "app keeps crashing"
python3 scripts/query.py "subscription keeps renewing"
python3 scripts/query.py "password email never arrives"
```

Observed results:

- `pytest` collected 7 tests and all 7 passed.
- Index build printed `indexed_articles=6`, `index=data/bm25_index.pkl`, and `df_store=data/df_store.json`.
- Compileall completed for `src` and `scripts`.
- `"app keeps crashing"` returned `KB-1001` first.
- `"subscription keeps renewing"` returned `KB-1003` first.
- `"password email never arrives"` returned `KB-1002` first.

One implementation issue was found during signoff: running `src/index.py` directly originally pickled `CorpusIndex` as `__main__.CorpusIndex`, which made `scripts/query.py` unable to unpickle the file. The entrypoint now re-imports `src.index.main()` when executed as a script, so generated pickles reference the stable `src.index.CorpusIndex` module path.
