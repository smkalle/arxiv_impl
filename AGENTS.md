# AGENTS.md

## Overview
Implements Meta's SIRA paper (arXiv:2605.06647): training-free retrieval bridging support-ticket vocabulary to KB articles via LLM enrichment + weighted BM25.

**Project root:** `sira_arXiv:2605.06647/` — all commands below run from there.

**Current state:** Iterations 1–3 implemented. Iterations 4–5 (FastAPI service, evaluation harness) are specified but not coded.

---

## Setup

```bash
pip install -r requirements.txt
# LLM backend (required for enrichment and sketch generation):
ollama pull qwen2.5:14b
ollama serve
```

No `setup.py` / `pyproject.toml`. No CI. No packaging. Run everything as scripts.

---

## Commands

All commands must be run from `sira_arXiv:2605.06647/` (not the repo root).

```bash
# Run all tests
python3 -m pytest tests/

# Run a single test file
python3 -m pytest tests/test_retrieve.py

# Build BM25 index from plain corpus
python3 src/index.py data/kb_corpus.jsonl --output data/bm25_index.pkl
# Also writes data/df_store.json automatically

# Offline enrichment batch job
python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl

# CLI query — plain BM25 (auto-builds index if missing)
python3 scripts/query.py "app keeps crashing"

# CLI query — full SIRA with audit trace (requires Ollama)
python3 scripts/query.py --sira "My app keeps crashing on login"
python3 scripts/query.py --sira "..." --tau 0.01 --weight 1.5

# Enrichment monitor UI (FastAPI, partial Iter 4 work)
uvicorn src.enrich_ui:app --reload
```

---

## Architecture

### Module layout (`src/`)
| File | Role |
|---|---|
| `index.py` | `CorpusIndex`: load JSONL → tokenize → `BM25Okapi` + DF counter → pickle |
| `enrich.py` | Offline batch: Ollama → 8–12 customer-language terms per KB article |
| `sketch.py` | Online: `generate_sketch(ticket_text)` → 8–12 KB-jargon terms via Ollama |
| `df_filter.py` | `validate_sketch_terms()`: keep terms where `0 < df ≤ τ×N` |
| `retrieve.py` | `retrieve()` plain BM25; `sira_retrieve()` full weighted pipeline |
| `enrich_ui.py` | FastAPI enrichment monitor (partial Iter 4 work, not the retrieval API) |

### Online pipeline (per ticket)
```
ticket → generate_sketch() → validate_sketch_terms() → weighted BM25
final_score = BM25(orig_tokens) + w × BM25(validated_sketch_tokens)
```
Fallback to plain BM25 if sketch fails or times out (`fallback_used=True`).

---

## Key gotchas

- **`python` vs `python3`:** `python` is not on PATH; always use `python3`.
- **Working directory matters:** `scripts/query.py` inserts its parent's parent into `sys.path`. `enrich_ui.py` mounts `src/static` and `src/templates` relative to CWD. Run everything from `sira_arXiv:2605.06647/`.
- **Tokenizer:** `nltk.word_tokenize`, lowercased, min token length 2, keeps only tokens with at least one alphanumeric char. Hard-coded in `src/index.py:tokenize()`.
- **`CorpusIndex` prefers `enriched_body` over `body`** when both fields exist (`src/index.py:44`). The DF counter also folds in `enriched_terms` as a separate set per article.
- **BM25 index is a pickle of the whole `CorpusIndex` object.** Rebuild after any corpus change.
- **`df_store.json` is written alongside the pickle** by `build_and_save()`. No need to pass a separate path; it defaults to `data/df_store.json`.
- **Global `_index` in `retrieve.py`:** must call `load_index()` before `retrieve()` or `sira_retrieve()`. Tests use `_set_index()` to inject fixtures and reset to `None` via `autouse` fixture.
- **Enrichment idempotency:** articles with `enriched_at >= last_updated` are skipped — requires both fields to be present in the JSONL.
- **`_parse_terms` in `enrich.py` drops:** terms present in original text (paper invariant), mixed alphanumeric tokens, and single-word tokens >8 chars (concatenation guard).
- **Env vars for LLM:** `OLLAMA_HOST` (default `http://localhost:11434`), `OLLAMA_MODEL` (default `qwen2.5:14b`). No `.env.example` yet.
- **`data/` files are not version-controlled** except `kb_corpus.jsonl`. The pickle, `df_store.json`, and enriched corpora are generated artifacts.

---

## Hyperparameters

| Param | Default | Description |
|---|---|---|
| `τ` (tau) | 0.01 | DF upper-bound filter for sketch validation |
| `w` | 1.5 | Sketch weight in combined BM25 score |
| Enrichment temp | 0.3 | Ollama temperature for article enrichment |
| Sketch temp | 0.1 | Ollama temperature for query sketch generation |

Hallucination rate = `len(rejected) / len(generated)`. If >20%, lower sketch temperature.

---

## Testing notes

- **38 tests, no integration tests** — all LLM calls are mocked via `unittest.mock`.
- `tests/conftest.py` defines `CORPUS_PATH` and `INDEX_PATH` relative to `tests/` parent (i.e., `data/kb_corpus.jsonl` must exist).
- The `enriched_index` fixture in `test_retrieve.py` pads to 100 articles so `τ=0.01` allows `df=1` terms to pass validation.
- SIRA tests patch `src.retrieve.generate_sketch` directly (not `src.sketch.generate_sketch`).

---

## What's not yet implemented (Iterations 4–5)

- `src/api.py` — `POST /retrieve`, `GET /health`, `POST /feedback` (FastAPI, bearer auth, Pydantic models)
- `src/models.py` — Pydantic request/response schemas
- `src/eval.py` — nDCG@10, Recall@5, MRR computation
- `scripts/run_ablations.py` — 5-experiment ablation table
- `tests/annotated_test_set.jsonl` — ≥20 hand-annotated ticket→KB pairs
- `.env.example`

See `ITERATIONS.md` for full sign-off checklists and expected CLI output for each iteration.

---

## Key references
- `sira-ticket-kb-spec.md` — full product spec, API schemas, evaluation thresholds, env vars (§13.3–13.4)
- `ITERATIONS.md` — implementation roadmap with per-iteration sign-off tests
- `CLAUDE.md` — architecture details, hyperparameter table, evaluation targets
