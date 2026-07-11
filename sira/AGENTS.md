# AGENTS.md — sira

Implements Meta's SIRA paper (arXiv:2605.06647): training-free retrieval bridging support-ticket vocabulary to KB articles via LLM enrichment + weighted BM25.

**Status:** Iterations 1–5 coded. Evaluation harness and ablation runner exist; test set is currently bootstrap placeholder data pending real annotations. See `CLAUDE.md` for run location and `ITERATIONS.md` for the per-iteration sign-off checklist.

---

## Setup

```bash
pip install -r requirements.txt
# LLM backend (required for enrichment and sketch generation):
ollama pull qwen2.5:3b
ollama serve
```

No `setup.py` / `pyproject.toml`. No CI. No packaging. Run everything as scripts.

---

## Commands

All commands run from `sira/` (not the repo root). Use `python3` — `python` is not on PATH.

```bash
# Run all tests (49 collected; no integration tests, LLM calls are mocked)
python3 -m pytest tests/
python3 -m pytest tests/test_retrieve.py        # single file

# Build BM25 index (preferred: import path avoids pickle module-name issues)
PYTHONPATH=. python3 -c "from src.index import build_and_save; build_and_save('data/enriched_corpus.jsonl','data/bm25_index.pkl')"

# Offline enrichment batch
PYTHONPATH=. python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl

# CLI query — plain BM25 (auto-builds index if missing)
python3 scripts/query.py "app keeps crashing"

# CLI query — full SIRA with audit trace (requires Ollama)
python3 scripts/query.py --sira "My app keeps crashing on login"
python3 scripts/query.py --sira "..." --tau 0.01 --weight 1.5

# Services (write pid/logs under sira/.{api,ui}_server.*)
./scripts/start_api.sh && ./scripts/start_ui.sh
# Equivalently: uvicorn src.api:app --reload  /  uvicorn src.enrich_ui:app --reload
```

---

## Architecture

| File (`src/`) | Role |
|---|---|
| `index.py` | `CorpusIndex`: load JSONL → tokenize → `BM25Okapi` + DF counter → pickle |
| `enrich.py` | Offline batch: Ollama → 8–12 customer-language terms per KB article |
| `sketch.py` | Online: `generate_sketch(ticket_text)` → 8–12 KB-jargon terms via Ollama |
| `df_filter.py` | `validate_sketch_terms()`: keep terms where `0 < df ≤ τ×N` |
| `retrieve.py` | `retrieve()` plain BM25; `sira_retrieve()` full weighted pipeline |
| `api.py` | FastAPI retrieval API (`app = FastAPI(...)`) |
| `enrich_ui.py` | FastAPI enrichment monitor (`app = FastAPI(...)`) — not the retrieval API |

Online pipeline (per ticket):
```
ticket → generate_sketch() → validate_sketch_terms() → weighted BM25
final_score = BM25(orig_tokens) + w × BM25(validated_sketch_tokens)
```
Falls back to plain BM25 if sketch fails or times out (`fallback_used=True`).

---

## Key gotchas (verified against current code)

- **Tokenizer** (`index.py:tokenize`): `nltk.word_tokenize`, lowercased, min token length 2, keeps only tokens with ≥1 alphanumeric char. Hard-coded.
- **`CorpusIndex` prefers `enriched_body` over `body`** when both exist (`index.py` `load_corpus`). The DF counter also folds in `enriched_terms` as a separate set per article.
- **BM25 index is a pickle of the whole `CorpusIndex` object.** Rebuild after any corpus change.
- **`df_store.json` is written alongside the pickle** by `build_and_save()`, defaulting to `<index_path>.parent / "df_store.json"` (i.e. `data/df_store.json`).
- **Global `_index` in `retrieve.py`:** must call `load_index()` before `retrieve()` or `sira_retrieve()` (raises `IndexNotLoadedError` otherwise). Tests inject fixtures via `_set_index()` and reset to `None` in an autouse fixture.
- **Enrichment idempotency:** articles with `enriched_at >= last_updated` are skipped — requires both fields present in the JSONL (`enrich.py` `enrich_corpus`).
- **`_parse_terms` in `enrich.py` drops:** terms present in original text (paper invariant), mixed alphanumeric tokens, and single-word tokens >8 chars (concatenation guard).
- **Env vars for LLM:** `OLLAMA_HOST` (default `http://localhost:11434`), `OLLAMA_MODEL` (default `qwen2.5:3b` — in both `enrich.py` and `sketch.py`). No `.env.example` yet.
- **`data/` files are not version-controlled** except `kb_corpus.jsonl`. The pickle, `df_store.json`, and enriched corpora are generated artifacts.

---

## Hyperparameters

| Param | Default | Where |
|---|---|---|
| `τ` (tau) | 0.01 | DF upper-bound filter for sketch validation (`sira_retrieve`) |
| `w` | 1.5 | Sketch weight in combined BM25 score (`sira_retrieve`) |
| Enrichment temp | 0.3 | `enrich.py` Ollama `options` |
| Sketch temp | 0.1 | `sketch.py` Ollama `options` |

Hallucination rate = `len(rejected) / len(sketch_terms)`. If >20%, lower sketch temperature.

---

## Testing notes

- 49 tests collected across `tests/test_{api,df_filter,enrich,eval,index,retrieve}.py`. No integration tests; LLM calls are injectable (`llm_call=` param) / mocked via `unittest.mock`.
- `tests/conftest.py` defines `CORPUS_PATH` and `INDEX_PATH` relative to the tests/ parent (`data/kb_corpus.jsonl`, `data/bm25_index.pkl` must exist).
- The `enriched_index` fixture in `test_retrieve.py` pads to ≥100 articles so `τ=0.01` allows `df=1` terms to pass validation.
- SIRA tests patch **`src.retrieve.generate_sketch`** directly (not `src.sketch.generate_sketch`) — `retrieve.py` imports the symbol into its own namespace.

---

## Remaining gaps

- `tests/annotated_test_set.jsonl` currently contains bootstrap placeholders; replace with hand-annotated ticket→KB pairs.
- `.env.example` is still missing.

## Key references
- `sira-ticket-kb-spec.md` — full product spec, API schemas, evaluation thresholds, env vars (§13.3–13.4)
- `ITERATIONS.md` — implementation roadmap with per-iteration sign-off tests
- `CLAUDE.md` — run location, core commands, artifact/git hygiene
