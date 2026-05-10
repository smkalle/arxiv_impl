# SIRA · Support Ticket → Resolution KB
## Product & Technical Specification

**Version:** 0.1 · Draft  
**Status:** Pre-prototype  
**Authors:** AI Product  
**Last Updated:** May 2026  
**Classification:** Internal

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Product Goals & Success Metrics](#2-product-goals--success-metrics)
3. [User Stories](#3-user-stories)
4. [System Overview](#4-system-overview)
5. [SIRA Mechanics Applied to This Use Case](#5-sira-mechanics-applied-to-this-use-case)
6. [Data Model](#6-data-model)
7. [Component Specifications](#7-component-specifications)
8. [API Contract](#8-api-contract)
9. [Retrieval Quality Thresholds](#9-retrieval-quality-thresholds)
10. [Prototype Sprint Plan](#10-prototype-sprint-plan)
11. [Open Questions & Risks](#11-open-questions--risks)
12. [Out of Scope](#12-out-of-scope)
13. [Appendix](#13-appendix)

---

## 1. Problem Statement

### 1.1 Current State

Support agents and automated triage systems attempt to match inbound customer tickets to resolution documents (KB articles, runbooks, past resolved tickets) using keyword search. This fails in three predictable ways:

| Failure Mode | Example | Impact |
|---|---|---|
| **Vocabulary gap** | Customer writes "app crashes on login", KB article says "authentication service segfault" | Zero BM25 overlap → no retrieval |
| **Jargon mismatch** | Customer writes "my subscription keeps renewing" vs KB "recurring billing idempotency failure" | Low recall |
| **Multi-round latency** | Agentic search reformulates query 3–5× to bridge the gap | 3–8 s end-to-end, high LLM cost |

The downstream cost: agents manually search, handle time increases, ticket deflection rate stays low, and KB investment is underutilized.

### 1.2 Root Cause

KB articles are written in **product/engineering language**. Inbound tickets are written in **customer language**. Existing BM25 indexes have no mechanism to bridge this vocabulary delta at retrieval time without multi-round LLM reformulation.

### 1.3 Opportunity

Meta's SIRA paper (arXiv:2605.06647, May 2026) provides a training-free method that:

- Enriches KB articles **once, offline** with the vocabulary a customer would actually use
- At query time, generates an "expected-resolution sketch" and validates terms against document-frequency statistics
- Executes a **single weighted BM25 call** — matching both customer query tokens and enriched KB vocabulary simultaneously

Result: multi-round search compressed into one step. Paper reports +15–25% nDCG@10 vs plain BM25, 10–30× cost reduction vs dense retrieval or multi-round agents.

---

## 2. Product Goals & Success Metrics

### 2.1 Goals

| Priority | Goal |
|---|---|
| P0 | Increase ticket-to-KB match recall by ≥15% vs current BM25 baseline |
| P0 | Match latency ≤ 500 ms per ticket (online path only; LLM enrichment is offline) |
| P1 | Produce an auditable match trace (which enriched terms fired and why) |
| P1 | Reuse enrichment pipeline as foundation for Phase 2 use cases (catalog, legal) |
| P2 | Reduce mean handle time (MHT) for agent-assisted tickets by 20% |

### 2.2 Success Metrics

| Metric | Baseline | Target | Measurement Method |
|---|---|---|---|
| nDCG@10 | Measure at kick-off | Baseline + 15% | Annotated test set, 200 tickets |
| Recall@5 | Measure at kick-off | Baseline + 20% | Same test set |
| P99 online latency | — | ≤ 500 ms | API timing log |
| Enrichment batch time | — | ≤ 4 h / 10k KB articles | Batch job timer |
| Agent adoption rate | — | ≥ 60% of suggestions acted on | Action log |
| KB coverage | — | ≥ 95% of KB articles enriched | Batch job status |

### 2.3 Non-Goals (for this prototype)

- Generating resolution text (this is retrieval, not generation)
- Training a custom model
- Replacing the existing ticketing system UI
- Achieving real-time enrichment on newly published KB articles (batch + cron is sufficient)

---

## 3. User Stories

### 3.1 Primary — Support Agent (Manual Workflow)

```
As a support agent reviewing an inbound ticket,
I want the system to surface the top 5 KB articles most likely to resolve it,
with a short explanation of why each was matched,
so I can resolve the ticket faster without manual searching.
```

**Acceptance criteria:**
- Match results appear within 500 ms of ticket submission
- Each result shows: KB article title, match score, matched enriched terms highlighted
- Agent can mark a result as "used" or "not helpful" (feedback loop)

### 3.2 Secondary — Automated Triage System

```
As the automated triage pipeline,
I want a retrieval API that accepts a raw ticket text
and returns ranked KB article IDs with confidence scores,
so I can auto-suggest or auto-resolve Tier 1 tickets.
```

**Acceptance criteria:**
- REST API: `POST /retrieve` accepts `{ "ticket_text": "..." }`, returns ranked KB list
- Response includes `matched_terms` array for audit
- Degrades gracefully if LLM sketch generation fails (falls back to plain BM25)

### 3.3 Tertiary — KB Manager

```
As a KB manager,
I want to see which enrichment terms are driving retrievals,
so I can identify gaps in KB article vocabulary and improve future articles.
```

**Acceptance criteria:**
- Audit log queryable by KB article ID
- Shows top 10 enriched terms per article and their retrieval hit frequency

---

## 4. System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                        OFFLINE PIPELINE (Run Once + Re-run on KB updates)
│                                                                 │
│  KB Articles (raw)                                              │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────┐    LLM (Qwen2.5-14b / Ollama)                │
│  │  Enrichment  │◄── "Generate 8-12 customer-language synonyms  │
│  │   Batch Job  │     absent from this article"                 │
│  └──────┬──────┘                                               │
│         │ enriched_doc = original_text + synonym_terms          │
│         ▼                                                       │
│  ┌─────────────┐                                               │
│  │  DF Counter  │  document_frequency[term] = count across corpus│
│  │  (JSON/Redis)│                                               │
│  └──────┬──────┘                                               │
│         ▼                                                       │
│  ┌─────────────┐                                               │
│  │  BM25 Index  │  Indexed on enriched corpus                  │
│  │ (rank-bm25   │                                               │
│  │  → Elastic)  │                                               │
│  └─────────────┘                                               │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│                        ONLINE PATH (Per ticket, < 500 ms)       │
│                                                                 │
│  Inbound Ticket Text                                            │
│       │                                                         │
│       ▼                                                         │
│  ┌─────────────┐    LLM (same model, low temperature)          │
│  │ Query Sketch │◄── "Generate expected resolution vocabulary   │
│  │  Generator   │     missing from this ticket"                 │
│  └──────┬──────┘                                               │
│         │ sketch_terms[]                                        │
│         ▼                                                       │
│  ┌─────────────┐                                               │
│  │DF Validation │  keep term if: df > 0 AND df ≤ τ × N         │
│  │   Filter     │  τ = 0.01, N = corpus size                   │
│  └──────┬──────┘                                               │
│         │ validated_terms[]                                     │
│         ▼                                                       │
│  ┌─────────────────────────────────┐                           │
│  │  Weighted BM25 Retrieval        │                           │
│  │  score = BM25(orig_q) + w×BM25(sketch_q)                   │
│  │  w = 1.5 (tunable)              │                           │
│  └──────────────┬──────────────────┘                           │
│                 │                                               │
│                 ▼                                               │
│  Top-K KB Articles + matched_terms[] + scores                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## 5. SIRA Mechanics Applied to This Use Case

### 5.1 Offline: KB Article Enrichment

**Prompt template:**

```
You are an expert support knowledge-base indexer.
Given the KB article below, generate 8–12 NEW discriminative search terms
that a customer would use when experiencing the problem described, but that
DO NOT appear in the article text.

Focus on:
- Plain customer language equivalents of technical jargon
- Common error messages a user might see (colloquial forms)
- Related symptoms that imply this root cause
- Abbreviations, typos, and alternate product names customers actually use

Output ONLY a comma-separated list. No explanations. No numbering.

KB Article:
{article_text}
```

**Output:** Appended to article text as space-separated tokens. Original text preserved.

**DF validation (corpus-side):** No lower-bound filter at enrichment time (new terms have DF=0 initially and will receive DF=1 after indexing). Upper-bound pruning applied during query validation, not here.

### 5.2 Online: Query Sketch Generation

**Prompt template:**

```
You are a support resolution expert.
Given the customer ticket below, generate an "expected resolution vocabulary sketch":
8–12 key technical terms, product component names, or KB jargon that would
likely appear in the article that resolves this ticket, but are ABSENT from
the ticket text itself.

Do NOT guess the actual answer. Generate vocabulary bridges only.
Output ONLY a comma-separated list. No explanations.

Customer Ticket:
{ticket_text}
```

### 5.3 DF Validation

```python
def validate_sketch_terms(terms, df_counter, N, tau=0.01):
    validated = []
    for term in terms:
        df = df_counter.get(term.lower(), 0)
        if df > 0 and df <= tau * N:   # exists in corpus AND not too common
            validated.append(term.lower())
    return validated
```

**Rationale for τ = 0.01:** Terms appearing in > 1% of KB articles are too generic to discriminate (e.g., "error", "click", "account"). Tune τ up if recall is too low; tune down if precision drops.

### 5.4 Weighted BM25 Retrieval

```python
def retrieve(ticket_text, top_k=5, w=1.5):
    q_orig = tokenize(ticket_text)
    sketch = generate_sketch(ticket_text)                   # LLM call
    q_exp  = validate_sketch_terms(sketch, df_counter, N)  # DF filter

    scores_orig = bm25.get_scores(q_orig)
    scores_exp  = bm25.get_scores(q_exp) if q_exp else [0.0] * len(scores_orig)

    final_scores = [s1 + w * s2 for s1, s2 in zip(scores_orig, scores_exp)]

    ranked = sorted(enumerate(final_scores), key=lambda x: x[1], reverse=True)[:top_k]
    return [(kb_articles[i], score, q_exp) for i, score in ranked]
```

**Weight w = 1.5** (paper default). Increase w if enriched-term signal is trusted; decrease if hallucinated sketches degrade precision.

---

## 6. Data Model

### 6.1 KB Article (Input)

```json
{
  "article_id": "KB-20341",
  "title": "Authentication service 503 on mobile clients",
  "body": "...",
  "product_area": "auth",
  "last_updated": "2026-03-10",
  "tags": ["login", "mobile", "503"]
}
```

### 6.2 Enriched Article (Stored)

```json
{
  "article_id": "KB-20341",
  "title": "Authentication service 503 on mobile clients",
  "original_body": "...",
  "enriched_body": "... app wont open keeps crashing login loop sign in broken cant log in 503 error phone app stuck loading",
  "enriched_terms": [
    "app wont open", "keeps crashing", "login loop",
    "sign in broken", "cant log in", "503 error",
    "phone app", "stuck loading"
  ],
  "enriched_at": "2026-05-01T02:14:00Z",
  "model_used": "qwen2.5:14b"
}
```

### 6.3 Retrieval Request

```json
{
  "ticket_id": "TKT-998812",
  "ticket_text": "My app keeps crashing whenever I try to log in. Been happening since yesterday.",
  "top_k": 5,
  "weight_w": 1.5
}
```

### 6.4 Retrieval Response

```json
{
  "ticket_id": "TKT-998812",
  "results": [
    {
      "article_id": "KB-20341",
      "title": "Authentication service 503 on mobile clients",
      "score": 14.72,
      "matched_original_terms": ["log", "app"],
      "matched_enriched_terms": ["keeps crashing", "login loop", "phone app"],
      "snippet": "When the authentication service returns a 503..."
    }
  ],
  "sketch_terms_generated": ["authentication failure", "503 error", "session token", "mobile crash"],
  "sketch_terms_validated": ["503 error", "mobile crash"],
  "sketch_terms_rejected": ["authentication failure", "session token"],
  "latency_ms": 312
}
```

### 6.5 DF Store

```json
{
  "app": 412,
  "authentication": 87,
  "503 error": 14,
  "keeps crashing": 9,
  "mobile crash": 6
}
```

Stored as: JSON file (prototype) → Redis hash (production).

---

## 7. Component Specifications

### 7.1 Enrichment Batch Job

| Property | Value |
|---|---|
| Trigger | Manual (prototype) → Cron daily or on KB publish event |
| Input | KB article corpus (JSON/CSV export or direct DB read) |
| LLM | Ollama Qwen2.5-14b, temp=0.3, max_tokens=200 |
| Parallelism | Batch size 10, ThreadPoolExecutor, rate-limited to 5 req/s |
| Output | `enriched_corpus.jsonl` + `df_store.json` |
| Idempotency | Skip articles where `enriched_at` is newer than `last_updated` |
| Error handling | Retry × 3 on LLM failure; log + skip on persistent failure |
| Estimated throughput | ~200 articles/hour on local Qwen2.5-14b; ~2000/hour on cloud API |

### 7.2 BM25 Index

| Property | Value |
|---|---|
| Prototype | `rank-bm25` (BM25Okapi), in-memory, serialized to disk |
| Production (>10k articles) | Elasticsearch 8.x with BM25 similarity, enriched_body field |
| Tokenizer | `nltk.word_tokenize`, lowercase, min token length 2 |
| Index refresh | Rebuild after each enrichment batch run |
| Storage | ~50 MB for 10k articles with enriched text |

### 7.3 Query Sketch Generator

| Property | Value |
|---|---|
| Model | Same as enrichment (Qwen2.5-14b / Ollama) |
| Temperature | 0.1 (low variance — we want consistent vocabulary bridging) |
| Max tokens | 150 |
| Timeout | 3 s hard timeout; on failure, fall back to plain BM25 |
| Caching | Cache `(hash(ticket_text), model_version)` → sketch_terms, TTL 24h |

### 7.4 DF Validation Filter

| Property | Value |
|---|---|
| τ (tau) | 0.01 (tunable per domain) |
| Lower bound | df > 0 (term must exist in enriched corpus) |
| Upper bound | df ≤ τ × N |
| Storage | JSON file → Redis (production) |
| Refresh | Rebuild with each BM25 index rebuild |

### 7.5 Retrieval API (FastAPI)

| Property | Value |
|---|---|
| Framework | FastAPI |
| Endpoint | `POST /retrieve` |
| Auth | Internal service token (Bearer) |
| Max ticket length | 4,000 characters (truncate beyond) |
| Default top_k | 5 |
| Default w | 1.5 |
| Response format | JSON (see §6.4) |
| Health check | `GET /health` |

### 7.6 Feedback Loop (Phase 2)

Agent actions logged to `retrieval_feedback` table:
- `result_used` — agent applied this KB article to resolve the ticket
- `result_not_helpful` — article was surfaced but irrelevant
- `ticket_resolved` — binary resolution flag

Feedback used to: (a) tune τ and w, (b) flag low-quality KB articles for review, (c) compute agent adoption rate metric.

---

## 8. API Contract

### 8.1 `POST /retrieve`

**Request:**

```http
POST /retrieve
Authorization: Bearer <token>
Content-Type: application/json

{
  "ticket_id": "TKT-998812",
  "ticket_text": "My app keeps crashing whenever I try to log in.",
  "top_k": 5,
  "weight_w": 1.5
}
```

**Response 200:**

```json
{
  "ticket_id": "TKT-998812",
  "results": [ /* see §6.4 */ ],
  "sketch_terms_generated": [...],
  "sketch_terms_validated": [...],
  "sketch_terms_rejected": [...],
  "fallback_used": false,
  "latency_ms": 312
}
```

**Response 200 (fallback — LLM sketch failed):**

```json
{
  "ticket_id": "TKT-998812",
  "results": [ /* plain BM25 results */ ],
  "fallback_used": true,
  "fallback_reason": "LLM timeout after 3000ms",
  "latency_ms": 45
}
```

**Error responses:**

| Code | Condition |
|---|---|
| 400 | `ticket_text` missing or empty |
| 413 | `ticket_text` > 4,000 characters (before truncation warning) |
| 503 | BM25 index not loaded |

### 8.2 `GET /health`

```json
{
  "status": "ok",
  "bm25_index_loaded": true,
  "df_store_loaded": true,
  "corpus_size": 3842,
  "index_built_at": "2026-05-07T02:30:00Z",
  "llm_backend": "ollama:qwen2.5:14b"
}
```

### 8.3 `POST /feedback`

```json
{
  "ticket_id": "TKT-998812",
  "article_id": "KB-20341",
  "action": "result_used" | "result_not_helpful",
  "agent_id": "AGT-112"
}
```

---

## 9. Retrieval Quality Thresholds

### 9.1 Evaluation Protocol

- **Test set:** 200 manually annotated ticket–KB article pairs (50 Tier-1, 100 Tier-2, 50 edge cases with high vocabulary gap)
- **Annotators:** 2 senior support agents, adjudicated by support lead
- **Metrics computed:** nDCG@5, nDCG@10, Recall@5, Recall@10, MRR

### 9.2 Go/No-Go Thresholds for Prototype Handoff

| Metric | Minimum to proceed |
|---|---|
| nDCG@10 improvement vs baseline | ≥ +10% |
| Recall@5 improvement vs baseline | ≥ +15% |
| P99 online latency | ≤ 500 ms |
| Sketch fallback rate | ≤ 10% of requests |
| Enriched term hallucination rate | ≤ 20% of generated terms rejected by DF filter |

> Hallucination rate = `len(sketch_terms_rejected) / len(sketch_terms_generated)`. High hallucination → reduce model temperature or tighten prompt.

### 9.3 Ablation Runs Required

| Experiment | Purpose |
|---|---|
| Baseline BM25 (no enrichment, no sketch) | Establishes floor |
| Enrichment only, no sketch | Tests offline enrichment contribution in isolation |
| Sketch only, no enrichment | Tests online expansion contribution in isolation |
| Full SIRA (enrichment + sketch + DF filter) | Expected winner |
| SIRA with w tuning (w = 1.0, 1.5, 2.0) | Find optimal weight for this corpus |

---

## 10. Prototype Sprint Plan

### Week 1 · Corpus Pipeline + Baseline

| Day | Task | Owner |
|---|---|---|
| 1 | Export KB articles to `kb_corpus.jsonl` (title + body, 1k–5k articles) | Data Eng |
| 1 | Stand up Ollama Qwen2.5-14b locally (or cloud endpoint) | Infra |
| 2 | Build and run enrichment batch job on 500 articles | AI Eng |
| 3 | Build DF counter, serialize to `df_store.json` | AI Eng |
| 3 | Build BM25 index on enriched corpus | AI Eng |
| 4 | Baseline evaluation: plain BM25 on 50 test tickets | AI Eng |
| 5 | Review enrichment quality with support lead (sanity check terms) | PM + Support |

**Week 1 exit criteria:** Enrichment batch runs end-to-end. Baseline nDCG@10 measured.

### Week 2 · SIRA Core + Eval

| Day | Task | Owner |
|---|---|---|
| 1–2 | Implement query sketch generator + DF validation | AI Eng |
| 2–3 | Implement weighted BM25 retrieval function | AI Eng |
| 3 | Run 5 ablation experiments on test set | AI Eng |
| 4 | Tune τ and w based on ablation results | AI Eng + PM |
| 5 | Full eval on 200-ticket test set | AI Eng |

**Week 2 exit criteria:** SIRA vs baseline delta measured. Go/no-go decision on thresholds in §9.2.

### Week 3 · API + Agent UI + Handoff

| Day | Task | Owner |
|---|---|---|
| 1–2 | FastAPI wrapper: `/retrieve`, `/health`, `/feedback` | Backend Eng |
| 2 | Audit log: store `sketch_terms_generated/validated/rejected` per request | Backend Eng |
| 3 | Lightweight agent UI: ticket text → top 5 KB results with term highlights | Frontend Eng |
| 4 | Load test: 50 concurrent requests, verify P99 ≤ 500 ms | Infra |
| 5 | Demo to stakeholders. Document Elasticsearch migration path. | PM |

**Week 3 exit criteria:** API live, agent UI usable, latency targets met, stakeholder sign-off.

---

## 11. Open Questions & Risks

### 11.1 Open Questions

| # | Question | Owner | Due |
|---|---|---|---|
| OQ-1 | What is the current KB article count and export format? | Data Eng | Week 1 Day 1 |
| OQ-2 | Do KB articles already have structured product-area tags we can use to tune enrichment prompts per domain? | Support / KB Mgr | Week 1 Day 2 |
| OQ-3 | Is Ollama permitted to process KB article content, or do we need an air-gapped LLM? | Security | Week 1 Day 1 |
| OQ-4 | What is the ground-truth annotation source for the 200-ticket test set? (CSAT scores? Agent-marked resolved tickets?) | Support Ops | Week 1 Day 3 |
| OQ-5 | What is the expected real-time ticket volume (req/s) in production? (Determines whether rank-bm25 or Elasticsearch is needed from Week 1) | Support Ops | Week 1 Day 1 |

### 11.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| **KB article quality is poor** — stale, duplicated, or very short articles degrade enrichment | Medium | High | Audit top 100 articles before enrichment. Filter articles < 200 words. |
| **LLM enrichment hallucination** — generated terms are plausible-sounding but not actually useful for this corpus | Medium | Medium | DF validation filter rejects terms absent from corpus. Manual spot-check in Week 1. |
| **Sketch generation latency** — Qwen2.5-14b takes > 1 s per query on CPU | High (CPU-only) | High | Use GPU instance for prototype, or switch to Qwen2.5-7b. Pre-warm model. |
| **Vocabulary gap is narrower than expected** — baseline BM25 already performs well | Low | Medium | Baseline eval in Week 1 Day 4 will surface this immediately. |
| **Data residency / compliance block** — KB content cannot leave on-prem | Low | High | OQ-3 resolves this. Air-gapped Ollama is the fallback. |
| **Test set annotation disagreement** — support agents disagree on ground truth | Medium | Medium | Adjudication protocol. Kappa score > 0.7 required before evaluation. |

---

## 12. Out of Scope

The following are explicitly excluded from this prototype:

- **Answer generation** — this spec is retrieval-only; no LLM-generated resolution text
- **Fine-tuning** — SIRA is training-free; no model training or fine-tuning
- **Multi-modal tickets** — screenshots, attachments, voice transcripts are not in scope
- **Real-time KB enrichment** — newly published articles enriched on next batch run (next-day), not instantly
- **Cross-language tickets** — English-only for prototype; multilingual is Phase 3
- **Ticket routing / assignment** — retrieval only, not downstream workflow orchestration
- **Elasticsearch migration** — documented as a path but not implemented in prototype

---

## 13. Appendix

### 13.1 Reference: SIRA Paper

- **arXiv:** 2605.06647 (May 2026)
- **Authors:** Meta AI
- **Key claims:** Training-free. Outperforms dense retrievers and multi-round agents on BEIR benchmarks. Single BM25 call per query.
- **Key hyperparameters:** τ = 0.01 (DF upper bound), w = 1.5 (sketch weight)

### 13.2 Dependencies

```
# Python
rank-bm25>=0.2.2
fastapi>=0.111.0
uvicorn>=0.29.0
ollama>=0.2.0
nltk>=3.8.1
tqdm>=4.66.0
pydantic>=2.7.0

# Optional (production scaling)
elasticsearch>=8.13.0
redis>=5.0.4
```

### 13.3 Environment Variables

```bash
OLLAMA_HOST=http://localhost:11434      # or remote Ollama endpoint
OLLAMA_MODEL=qwen2.5:14b               # enrichment + sketch model
BM25_INDEX_PATH=./data/bm25_index.pkl
DF_STORE_PATH=./data/df_store.json
ENRICHED_CORPUS_PATH=./data/enriched_corpus.jsonl
SIRA_TAU=0.01
SIRA_WEIGHT_W=1.5
API_TOKEN=<internal_service_token>
```

### 13.4 File Structure

```
sira-ticket-kb/
├── data/
│   ├── kb_corpus.jsonl             # raw KB articles
│   ├── enriched_corpus.jsonl       # enriched articles
│   ├── df_store.json               # document frequency map
│   └── bm25_index.pkl              # serialized BM25 index
├── src/
│   ├── enrich.py                   # offline enrichment batch job
│   ├── index.py                    # BM25 index builder
│   ├── retrieve.py                 # SIRA retrieval function
│   ├── api.py                      # FastAPI app
│   └── eval.py                     # nDCG/recall evaluation
├── tests/
│   ├── test_retrieve.py
│   └── annotated_test_set.jsonl    # 200 ticket-KB pairs
├── scripts/
│   └── export_kb.py                # KB export helper
├── .env.example
├── requirements.txt
└── README.md
```

### 13.5 Related Decisions

| Decision | Rationale |
|---|---|
| Ollama over cloud LLM API | Data residency, zero marginal cost, offline-first architecture |
| rank-bm25 over Elasticsearch for prototype | Zero infra overhead; validated swap path documented for production |
| Single shared model for enrichment + sketch | Reduces operational surface; both tasks are vocabulary generation |
| τ = 0.01 as starting point | Paper default; tune based on Week 2 ablation results |
| w = 1.5 as starting point | Paper default; tune based on Week 2 ablation results |
| No real-time enrichment | Batch is sufficient; enrichment quality > enrichment speed for KB content |

---

*This document is a living spec. Update version and status fields on each revision. Major changes require PM sign-off before implementation.*
