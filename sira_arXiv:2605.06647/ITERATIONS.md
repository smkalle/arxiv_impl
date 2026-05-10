# SIRA Implementation — Iterative Plan

Each iteration is self-contained and shippable. Later iterations extend earlier ones without breaking them.

---

## Iteration 1 — Corpus Loader + Plain BM25 + CLI Query

**Goal:** Working retrieval baseline before any enrichment.

### Deliverables
| File | Purpose |
|---|---|
| `src/index.py` | Load `kb_corpus.jsonl`, tokenize with nltk, build `BM25Okapi`, serialize to `data/bm25_index.pkl` |
| `src/retrieve.py` | `retrieve(query, top_k=5) → list[dict]` — plain BM25, no LLM |
| `scripts/query.py` | CLI: `python scripts/query.py "app keeps crashing"` |
| `requirements.txt` | Pin all deps |
| `data/kb_corpus.jsonl` | Sample corpus (10–20 hand-written KB articles) for testing |

### Sign-off Tests (`tests/test_index.py`, `tests/test_retrieve.py`)
- [ ] Load corpus: correct article count, no empty docs
- [ ] Tokenizer: lowercased, min length 2, punctuation stripped
- [ ] `retrieve("authentication 503")` returns article containing "503" in top 3
- [ ] `retrieve` on empty corpus raises `IndexNotLoadedError`
- [ ] `retrieve` with unknown query returns empty list, not exception

### Human-Verifiable Interface
```bash
python scripts/query.py "app keeps crashing on login"
# Expected output:
# Rank 1 [score=8.42] KB-20341 — Authentication service 503 on mobile clients
#   Snippet: When the authentication service returns a 503...
# Rank 2 [score=5.11] KB-10042 — ...
```

---

## Iteration 2 — Offline Enrichment Batch Job

**Goal:** LLM-enriched corpus built and indexed. DF store available for later use.

**Builds on:** Iteration 1 (replaces plain corpus in BM25 index with enriched corpus).

### Deliverables
| File | Purpose |
|---|---|
| `src/enrich.py` | Batch enrichment: Ollama → 8–12 new terms per article, appended to body |
| `src/index.py` (updated) | Accept either plain or enriched corpus; build `df_store.json` after indexing |
| `data/enriched_corpus.jsonl` | Output of enrichment run |
| `data/df_store.json` | `{term: doc_frequency}` map |

**Enrichment prompt:** See spec §5.1. LLM settings: temp=0.3, max_tokens=200, retry×3.  
**Idempotency:** Skip articles where `enriched_at > last_updated`.

### Sign-off Tests (`tests/test_enrich.py`)
- [ ] Enriched terms are absent from original article text (core paper invariant)
- [ ] Output JSONL has `enriched_terms`, `enriched_at`, `model_used` fields
- [ ] Re-running enrichment on already-enriched corpus does not re-enrich (idempotency)
- [ ] LLM failure on one article: logs error, skips article, continues batch
- [ ] DF store: `df_counter["app"] > 0` after indexing enriched corpus
- [ ] DF store: every term in any enriched article appears in df_store

### Human-Verifiable Interface
```bash
python src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl
# Expected output:
# Enriching 20 articles [██████████] 20/20
# Sample — KB-20341 new terms: ["app wont open", "keeps crashing", "login loop", ...]
# DF store written: 1,847 unique terms
# Skipped 0 (already current), failed 0
```
Manually inspect a few entries in `data/enriched_corpus.jsonl` — confirm terms read like customer language, not engineering jargon.

---

## Iteration 3 — Online Sketch + DF Validation + Weighted BM25

**Goal:** Full SIRA retrieval function. CLI shows the audit trace.

**Builds on:** Iteration 2 (requires enriched BM25 index and df_store).

### Deliverables
| File | Purpose |
|---|---|
| `src/retrieve.py` (updated) | `sira_retrieve(query, top_k, w, tau)` — sketch → DF filter → weighted BM25 |
| `src/sketch.py` | `generate_sketch(ticket_text) → list[str]` — LLM call, temp=0.1, 3s timeout |
| `src/df_filter.py` | `validate_sketch_terms(terms, df_counter, N, tau) → list[str]` |
| `scripts/query.py` (updated) | Add `--sira` flag to show full audit trace |

**Weighted BM25 formula:** `final_score = BM25(orig_tokens) + w × BM25(validated_sketch_tokens)`  
**Fallback:** On sketch timeout/failure, set `fallback_used=True`, return plain BM25 result.

### Sign-off Tests (`tests/test_retrieve.py`, `tests/test_df_filter.py`)
- [ ] `validate_sketch_terms`: rejects terms with df=0 (not in corpus)
- [ ] `validate_sketch_terms`: rejects terms with df > τ×N (too common)
- [ ] `validate_sketch_terms`: keeps terms with 0 < df ≤ τ×N
- [ ] `sira_retrieve` score is strictly ≥ plain BM25 score when sketch validates at least one term
- [ ] `sira_retrieve` returns `fallback_used=True` when sketch generator raises timeout
- [ ] `sira_retrieve` result includes `sketch_terms_generated`, `sketch_terms_validated`, `sketch_terms_rejected`
- [ ] Hallucination rate field: `len(rejected)/len(generated)` is correct

### Human-Verifiable Interface
```bash
python scripts/query.py --sira "My app keeps crashing whenever I try to log in"
# Expected output:
# Sketch generated:  ["authentication failure", "503 error", "session token", "mobile crash", ...]
# Sketch validated:  ["503 error", "mobile crash"]       (df > 0, df ≤ τ×N)
# Sketch rejected:   ["authentication failure", "session token"]  (too common)
# Hallucination rate: 50%
#
# Rank 1 [score=14.72] KB-20341 — Authentication service 503 on mobile clients
#   Matched original: ["log", "app"]
#   Matched enriched: ["keeps crashing", "login loop", "mobile crash"]
```

---

## Iteration 4 — FastAPI Service

**Goal:** HTTP API matching the spec contract. Suitable for integration by other systems.

**Builds on:** Iteration 3 (wraps `sira_retrieve` in FastAPI).

### Deliverables
| File | Purpose |
|---|---|
| `src/api.py` | FastAPI app: `POST /retrieve`, `GET /health`, `POST /feedback` |
| `src/models.py` | Pydantic request/response models (spec §6.3–6.5) |
| `tests/test_api.py` | HTTP-level tests via `httpx.AsyncClient` |
| `.env.example` | All env vars from spec §13.3 |

**Behaviour:**
- Truncate `ticket_text` to 4,000 chars
- Bearer token auth on `/retrieve` and `/feedback`
- `/health` reports `bm25_index_loaded`, `corpus_size`, `index_built_at`
- Log every request's `sketch_terms_*` fields for audit

### Sign-off Tests (`tests/test_api.py`)
- [ ] `POST /retrieve` happy path: returns ranked results, all audit fields present
- [ ] `POST /retrieve` with `fallback_used=true` when LLM is unavailable
- [ ] `POST /retrieve` with missing `ticket_text` → 400
- [ ] `POST /retrieve` with `ticket_text` > 4000 chars → truncates, returns warning field
- [ ] `GET /health` returns `bm25_index_loaded: true` after startup, `false` before index load
- [ ] `POST /retrieve` without Bearer token → 401
- [ ] Response `latency_ms` field is a positive integer

### Human-Verifiable Interface
```bash
uvicorn src.api:app --reload
# Browse to http://localhost:8000/docs  →  Swagger UI with all 3 endpoints

curl -s -X POST http://localhost:8000/retrieve \
  -H "Authorization: Bearer dev-token" \
  -H "Content-Type: application/json" \
  -d '{"ticket_id":"TKT-001","ticket_text":"app keeps crashing on login"}' | jq .

curl -s http://localhost:8000/health | jq .
```

---

## Iteration 5 — Evaluation Harness + Ablation Runner

**Goal:** Quantified comparison of all five ablation variants. Go/no-go decision against spec thresholds.

**Builds on:** Iteration 3 (calls retrieve functions directly, no HTTP layer needed).

### Deliverables
| File | Purpose |
|---|---|
| `src/eval.py` | `compute_metrics(results, qrels) → {ndcg@5, ndcg@10, recall@5, recall@10, mrr}` |
| `scripts/run_ablations.py` | Runs all 5 ablation experiments, prints comparison table |
| `tests/annotated_test_set.jsonl` | ≥20 hand-annotated ticket→KB pairs (scaled to 200 before production) |
| `tests/test_eval.py` | Unit tests for metric functions |

**Five ablation experiments** (spec §9.3):
1. Baseline BM25 (no enrichment, no sketch)
2. Enrichment only (enriched index, plain BM25 query)
3. Sketch only (plain index, sketch-expanded query)
4. Full SIRA (enriched index + sketch, w=1.5)
5. w sweep (full SIRA at w=1.0, w=1.5, w=2.0)

### Sign-off Tests (`tests/test_eval.py`)
- [ ] `compute_metrics` with perfect ranking returns nDCG@10=1.0
- [ ] `compute_metrics` with no relevant docs returned returns recall@5=0.0
- [ ] `compute_metrics` with known ranking matches hand-calculated nDCG value (± 0.001)
- [ ] Ablation runner produces output for all 5 experiments without error
- [ ] Full SIRA nDCG@10 ≥ baseline nDCG@10 + 10% on test set (go/no-go gate)
- [ ] Full SIRA Recall@5 ≥ baseline Recall@5 + 15% on test set (go/no-go gate)

### Human-Verifiable Interface
```bash
python scripts/run_ablations.py --test-set tests/annotated_test_set.jsonl

# Expected output:
# ┌─────────────────────────────┬────────────┬────────────┬──────────┬──────────┬────────┐
# │ Experiment                  │ nDCG@5     │ nDCG@10    │ Recall@5 │ Recall@10│ MRR    │
# ├─────────────────────────────┼────────────┼────────────┼──────────┼──────────┼────────┤
# │ 1. Baseline BM25            │ 0.312      │ 0.341      │ 0.380    │ 0.460    │ 0.298  │
# │ 2. Enrichment only          │ 0.358      │ 0.389      │ 0.430    │ 0.510    │ 0.341  │
# │ 3. Sketch only              │ 0.334      │ 0.362      │ 0.400    │ 0.480    │ 0.318  │
# │ 4. Full SIRA (w=1.5)        │ 0.401      │ 0.432  ✓  │ 0.470  ✓ │ 0.560    │ 0.389  │
# │ 5. SIRA w=1.0               │ 0.385      │ 0.415      │ 0.455    │ 0.540    │ 0.372  │
# │ 5. SIRA w=2.0               │ 0.396      │ 0.427      │ 0.465    │ 0.550    │ 0.381  │
# └─────────────────────────────┴────────────┴────────────┴──────────┴──────────┴────────┘
# Go/No-Go: PASS  (nDCG@10 +26.7%, Recall@5 +23.7% vs baseline)
```

---

## Iteration Summary

| Iter | What you can do after | New test files | New human interface |
|---|---|---|---|
| 1 | Query plain BM25 corpus from CLI | `test_index.py`, `test_retrieve.py` | `scripts/query.py "..."` |
| 2 | Run enrichment batch, inspect generated terms | `test_enrich.py` | `src/enrich.py` with progress + sample output |
| 3 | Run full SIRA retrieve, see audit trace in CLI | `test_df_filter.py` (updated `test_retrieve.py`) | `scripts/query.py --sira "..."` |
| 4 | Call HTTP API, use Swagger UI | `test_api.py` | `curl /retrieve`, `/health`, `/docs` |
| 5 | Run ablations, see go/no-go verdict | `test_eval.py` | `scripts/run_ablations.py` table |
