# UC-1 · Enterprise Knowledge Search — Product & Technical Spec Plan

> **Composite score:** 8.7 / 10 · Ease 8 · Value 9 · Market 9  
> **Model:** `jina-embeddings-v5-omni-small` (default) · `jina-embeddings-v5-omni-nano` (cost SKU)  
> **Stack:** Chroma · FastAPI · Jina API ↔ self-hosted (config-switchable)  
> **License:** CC-BY-NC-4.0 — commercial agreement required before any GA deployment

---

## 00 · Document Map

13 sections in the full spec. Status reflects authoring readiness after this plan.

| # | Section | What it covers | Owner | Status |
|---|---|---|---|---|
| 01 | Problem Statement | Knowledge fragmentation pain, quantified cost, failed alternatives | Product | ✅ Ready |
| 02 | Solution Overview | 1-liner, 5 differentiators, Jina v5-omni rationale, backward-compat story | Product | ✅ Ready |
| 03 | System Architecture | Ingestion flow, embedding backend, vector DB, query layer, config toggle | Arch | 🔄 In progress |
| 04 | Data Model & Schema | Document record schema, modality metadata, Chroma collection design | Arch | ⚠️ Decision open |
| 05 | Ingestion Pipeline | Connectors, chunking strategy, batch embedding, idempotency, retry | Eng | ⚠️ Decision open |
| 06 | Retrieval & Query API | Query types, ANN config, re-ranking, response schema, latency SLAs | Eng | 🔄 In progress |
| 07 | Config & Switchability | `EMBEDDING_BACKEND` env var, Jina API ↔ local toggle, Matryoshka dim | Eng | ✅ Ready |
| 08 | Evals & Quality Gates | MIEB-Lite, Precision@5, latency p95, golden dataset methodology | Product + Eng | 🔲 TBD |
| 09 | NFRs & Constraints | Latency budgets, throughput, storage cost, VRAM, cold-start | Arch | 🔲 TBD |
| 10 | Security & Compliance | DPDP 2025, data residency, PII masking, ACL, CC-BY-NC-4.0 gating | Compliance | ⚠️ Decision open |
| 11 | Migration Path | Text index upgrade, zero-re-embedding proof, modality rollout phasing | Eng | ✅ Ready |
| 12 | GTM & Pricing | ICP, land-and-expand, SaaS vs. self-hosted SKU, commercial license path | Product | 🔲 TBD |
| 13 | Open Questions & Risks | Decision log, spike list, license risk, latency risk, vendor lock-in | All | 🔄 In progress |

---

## 01 · Context & Strategic Goals

### Problem
Enterprise knowledge lives in Confluence (text), Figma (screenshots), Loom (video), and Notion (PDFs). Employees run **3–5 separate searches** to find an answer that spans these systems. No cross-modal retrieval exists today.

### Jina v5-omni insight
- Backward-compatible with existing text indexes — **no re-embedding on day 1**
- Frozen text backbone — text quality doesn't regress when adding image/audio/video modalities
- Incremental modality onboarding — add Figma, then Loom, without touching existing embeddings

### Success criteria
| Metric | Target |
|---|---|
| Query latency (text) | p95 < 500ms (Jina API) · p95 < 400ms (self-hosted) |
| Query latency (image/audio) | p95 < 800ms |
| Retrieval quality | Precision@5 ≥ 0.80 · nDCG@10 ≥ 0.70 (image) |
| Migration | Zero re-embedding of existing text corpus |
| Backend switch | Jina API ↔ self-hosted via single env var, no code changes |
| Compliance | Commercial license + DPDP 2025 clearance before GA |

### Hard constraints
- **CC-BY-NC-4.0** — commercial license required before external SaaS GA
- **DPDP 2025** — India data residency compliance for employee-authored content
- **VRAM** — ≤ 8GB for omni-small self-hosted (A10G / RTX 4090)
- **Vector DB** — Chroma as default (pluggable interface)

---

## 02 · Problem Statement — Spec section brief

The full spec Section 1 must cover these three subsections:

**2.1 Current state**
Fragmented search UX across Confluence, Notion, Figma, Loom. No cross-modal context. Users context-switch between 3+ tools per query.

**2.2 Quantified pain**
Time-to-answer metric. % of queries that span modalities. Estimated hours/week per employee lost to cross-tool search. Source: Gartner benchmark or internal survey.

**2.3 Failed alternatives**
Why text-only embedding doesn't solve it. Why separate per-modality models increase infra cost. Why keyword search on metadata is insufficient for intent-based queries.

---

## 03 · Solution Overview — Spec section brief

**Core narrative**
A unified search layer that embeds text, image, audio, and PDF into a shared vector space using `jina-embeddings-v5-omni`. One Chroma collection. One query endpoint. Backward-compatible with existing text corpora from day 1.

**5 differentiators**
1. Shared vector space — no modality translation layer or bridge model
2. Text backward-compat — existing text indexes work without re-embedding
3. Incremental modality onboarding — add image/audio/video without touching text
4. Config-switchable backend — Jina API ↔ self-hosted via `EMBEDDING_BACKEND` env var
5. Matryoshka dims — tune storage vs. accuracy at query time (32 → 1024)

> **Author note:** The solution narrative must explicitly contrast against the "separate vision model pipeline" alternative. The frozen text backbone argument is the strongest trust-builder for enterprise buyers with existing Confluence/Notion investments.

---

## 04 · System Architecture

### End-to-end data flow

```
┌─────────────────────────────────────────────────────────────┐
│                    SOURCE CONNECTORS                         │
│  Confluence (REST) · Notion (API) · Loom (API) · Figma (API)│
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│               INGESTION LAYER                               │
│  Priority Queue (in-proc → Redis Streams in Sprint 3)       │
│  Document Pre-processor:                                     │
│    - Text: markdown strip → 512-token chunks                │
│    - Image: resize to 1024px longest edge                   │
│    - Audio: extract from Loom → 16kHz mono WAV              │
│    - PDF: pass path directly to Jina native render          │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│          EMBEDDING BACKEND (config-switchable)              │
│                                                             │
│  if EMBEDDING_BACKEND=jina_api:                             │
│    → POST api.jina.ai/v1/embeddings                         │
│    → task: retrieval.passage, dimensions: 512               │
│                                                             │
│  if EMBEDDING_BACKEND=local:                                │
│    → SentenceTransformer(jina-omni-small, bfloat16)         │
│    → model.encode(batch, batch_size=32)                     │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                  VECTOR STORE                               │
│  Chroma PersistentClient                                    │
│  Collection: multimodal-knowledge                           │
│  Distance: cosine · HNSW index                              │
│  Metadata: modality, source_system, asset_url,              │
│            acl_groups, created_at, chunk_index              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│               RETRIEVAL API (FastAPI)                       │
│  POST /search   → ANN query → optional re-rank → response  │
│  POST /ingest   → webhook push from source connectors       │
│  GET  /health   → backend status + index stats              │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│                     CLIENTS                                 │
│  Search UI (web / Slack bot) · Commerce Analytics Agent     │
└─────────────────────────────────────────────────────────────┘
```

### Backend switchability contract

```python
# Abstract interface — only import path that other modules use
class EmbeddingBackend(ABC):
    def embed(self, inputs: list) -> np.ndarray: ...

# Concrete implementations
class JinaAPIBackend(EmbeddingBackend): ...
class LocalBackend(EmbeddingBackend): ...

# Factory — driven by env var
def get_backend(config: Config) -> EmbeddingBackend:
    if config.EMBEDDING_BACKEND == "jina_api":
        return JinaAPIBackend(api_key=config.JINA_API_KEY)
    return LocalBackend(model_id=config.LOCAL_MODEL_ID)
```

---

## 05 · Data Model & Schema

### Document record (Chroma)

```python
{
  "id":        "src:confluence:PAGE_ID:chunk_3",
  "embedding": [float32 × EMBED_DIM],          # default 512 (Matryoshka)
  "document":  "raw text chunk or asset ref",
  "metadata": {
    "modality":          "text | image | audio | video | pdf",
    "source_system":     "confluence | notion | loom | figma",
    "asset_url":         "https://...",          # original source for deref
    "acl_groups":        ["eng-all", "design"],  # pre-filter on query
    "created_at":        "2026-05-01T10:00:00Z",
    "chunk_index":       3,
    "token_count":       487,
    "task_adapter_used": "retrieval",
    "matryoshka_dim":    512
  }
}
```

### Collection config

```python
collection = client.create_collection(
    name="multimodal-knowledge",
    metadata={"hnsw:space": "cosine", "hnsw:M": 16, "hnsw:ef_construction": 200}
)
```

> **Open Decision D-03:** Chunking strategy for PDFs — page-level (1 embed/page, recommended) vs. fixed 512-token window vs. semantic sentence split. Requires spike before this section is finalized.

---

## 06 · Ingestion Pipeline

### Connectors — Phase 1 (Sprint 1–2)

| Connector | API | Content extracted | Notes |
|---|---|---|---|
| Confluence | REST v2 | Pages (markdown), attachments (PDF, PNG) | Incremental via `updated_since` |
| Notion | Notion API | Pages → PDF export | Rate limit: 3 req/s |
| Figma | REST API | Frame PNG export, 1024px resize | Requires Figma token per workspace |
| Loom | Loom API | Video URL → 16 frames + audio | D-04 decision applies |

### Pre-processing per modality

```
text  → strip markdown → split 512 tokens w/ 64-token overlap
image → PIL resize (1024px longest edge) → encode as PIL object
audio → librosa.load(sr=16000, mono=True) → pass path to model
PDF   → pass file path directly → Jina native render
video → pre-extract 16 frames (imageio) + audio → fused encode
```

### Reliability

- **Idempotency:** Skip document if embedding hash (SHA256 of raw content) unchanged
- **Retry:** Exponential backoff on Jina API 429 (3 retries, max 60s delay)
- **Dead-letter:** Failed items → `failed_docs` collection with error metadata
- **Incremental crawl:** `updated_since` timestamp per source system, stored in config DB

---

## 07 · Retrieval & Query API

### POST /search — request contract

```json
{
  "query_text":      "How does the onboarding flow work?",
  "query_image_b64": null,
  "query_audio_url": null,
  "n_results":       10,
  "modality_filter": ["text", "image"],
  "source_filter":   ["confluence", "figma"],
  "task":            "retrieval"
}
```
At least one of `query_text`, `query_image_b64`, `query_audio_url` required. If multiple provided, inputs are fused into a single embedding via `model.encode((text, image, audio))`.

### POST /search — response schema

```json
{
  "results": [
    {
      "id":        "src:figma:FRAME_ID:0",
      "score":     0.91,
      "modality":  "image",
      "source":    "figma",
      "snippet":   "Onboarding flow — step 3 of 5",
      "asset_url": "https://figma.com/file/..."
    }
  ],
  "query_latency_ms": 187,
  "backend_used":     "jina_api"
}
```

### Latency SLAs

| Query type | p50 (Jina API) | p95 (Jina API) | p95 (self-hosted) |
|---|---|---|---|
| Text | < 150ms | < 500ms | < 400ms |
| Image | < 300ms | < 800ms | < 600ms |
| Audio | < 400ms | < 800ms | < 700ms |
| Fused (text+image) | < 400ms | < 1000ms | < 800ms |

**Matryoshka fallback:** If p95 budget exceeded, retry query at 256-dim truncation (< 2% nDCG loss based on MIEB-Lite benchmarks).

### Re-ranking (optional)

```
RERANK_ENABLED=true → cross-encoder on top-20 results → re-sort → return top-n
```
Text-only cross-encoder on snippet field (not raw embedding). Adds ~80ms. Configurable per request via `rerank: true` param.

---

## 08 · Config & Switchability

### Environment variables

```bash
# Core backend switch
EMBEDDING_BACKEND=jina_api           # or: local

# Jina API (required if backend=jina_api)
JINA_API_KEY=jina_xxxx

# Local model (required if backend=local)
LOCAL_MODEL_ID=jinaai/jina-embeddings-v5-omni-small
LOCAL_MODEL_DTYPE=bfloat16           # or: float16, float32

# Embedding configuration
EMBED_DIM=512                        # 32|64|128|256|512|768|1024
TASK_ADAPTER=retrieval               # retrieval|classification|clustering

# Retrieval
RERANK_ENABLED=false
N_RESULTS_DEFAULT=10

# Storage
CHROMA_PATH=/data/chroma             # local PersistentClient path

# Reliability
INGEST_BATCH_SIZE=32
INGEST_MAX_RETRIES=3
INGEST_RETRY_DELAY_S=5
```

### Module boundary rule
No code outside `backends/` may import from `JinaAPIBackend` or `LocalBackend` directly. All call sites use `get_backend(config)`. Enforced via import linting in CI.

---

## 09 · Evals & Quality Gates

### Gate definitions (go/no-go per sprint)

| Gate | Metric | Threshold | Sprint | Eval tool |
|---|---|---|---|---|
| Text retrieval | Precision@5 | ≥ 0.80 | Sprint 1 | Custom harness on 50 Confluence golden pairs |
| Text vs. baseline | Delta vs. BM25 | ≥ +5pp | Sprint 1 | Same harness |
| Image retrieval | nDCG@10 | ≥ 0.70 | Sprint 2 | MIEB-Lite |
| Cross-modal (Figma→Confluence) | Manual recall | ≥ 18/20 | Sprint 2 | 20 golden pairs |
| Latency (text, 100 concurrent) | p95 | < 500ms | Sprint 3 | Locust |
| Latency (image, 100 concurrent) | p95 | < 800ms | Sprint 3 | Locust |

### Golden dataset construction
- **50 text queries** from Confluence — curated by sampling real Confluence search logs
- **20 image→text pairs** — Figma frames manually mapped to their corresponding Confluence pages
- **Staleness management** — golden set versioned in Git; re-evaluate on any model or dim change

> The eval section of the full spec must document the golden dataset methodology explicitly. This is the highest-leverage section for enterprise buyer trust.

---

## 10 · NFRs & Constraints

### Performance

| Requirement | Target |
|---|---|
| Ingestion throughput (Jina API) | ≥ 50 docs/min |
| Ingestion throughput (local) | ≥ 20 docs/min |
| Index capacity (before sharding) | ≥ 500K documents |
| Cold start (local model, 8GB VRAM) | < 30s |
| Query p95 (text, Jina API) | < 500ms |
| Query p95 (image/audio, Jina API) | < 800ms |

### Infrastructure

| Component | MVP | Production |
|---|---|---|
| Embedding (self-hosted) | RTX 4090 (24GB) or A10G | Same — single GPU sufficient |
| Embedding (nano option) | 4GB VRAM, Mac M2/M3 via MLX | Same |
| Vector DB | Chroma PersistentClient (local) | Chroma Cloud or self-hosted cluster |
| Queue | In-process (Sprint 1–2) | Redis Streams (Sprint 3) |
| Deployment | Docker Compose (MVP) | Kubernetes optional — not required for MVP |

---

## 11 · Security & Compliance

### DPDP 2025
Embeddings derived from employee-authored content (Confluence pages, Loom recordings) are treated as personal data under DPDP 2025 Stage 2. Requirements:
- Consent manager integration before ingesting employee content
- Data principal deletion right — propagates to Chroma index (delete by `document_id` prefix)
- **PII masking layer** before any Jina API call (Jina API infra is non-India)
- Self-hosted backend for content classified as sensitive

### Access control
- Source-level ACL metadata (`acl_groups[]`) stored with every document
- **Pre-filter** on `acl_groups` at Chroma query time — result set never contains documents the caller cannot access
- Confluence space permissions → `acl_groups[]` mapping maintained by ingestion connector

### License gate
**CC-BY-NC-4.0 blocks all commercial deployment.**

| Path | Timeline | Notes |
|---|---|---|
| Elastic Inference Service | 1–2 weeks | Commercial rights included; fastest path |
| Direct Jina AI enterprise agreement | 4–8 weeks | More control over SLAs |

Internal tooling (non-revenue-generating) is exempt. External SaaS or any product with paying customers is blocked until license is cleared.

---

## 12 · Migration Path

### Phase 1 — Text-only (Sprint 1, Day 1 ready)
1. Swap embedding model to `jina-omni-small` — **no re-embedding required** (text backward-compat)
2. Enable Confluence + Notion connectors
3. Validate Precision@5 parity with previous text model
4. Ship: text search parity proven

### Phase 2 — Add image + PDF (Sprint 2, Week 5)
1. Enable Figma connector (PNG frame export)
2. Enable Notion PDF render (Jina native path)
3. Text queries now surface image/PDF results from same collection
4. Validate with MIEB-Lite gate (nDCG@10 ≥ 0.70)
5. **No existing text embeddings touched**

### Phase 3 — Add audio/video (Sprint 3, Week 7)
1. **Commercial license confirmed** — hard gate before this phase ships
2. Enable Loom connector (16-frame + audio extraction, fused embed)
3. Validate latency gate under load
4. Full omni-modal search live

### Rollback
Each modality is additive. Rollback = disable connector + `collection.delete(where={"modality": "video"})`. Text index untouched. Zero-downtime rollback per modality.

---

## 13 · GTM & Pricing

### ICP
- **Primary:** Mid-to-large tech companies (500–5000 employees) using Confluence + Notion + Loom + Figma simultaneously — common in eng-heavy SaaS companies
- **Secondary:** Internal platform teams building enterprise search for developer portals and internal knowledge bases

### Packaging

| SKU | Backend | Pricing model | Notes |
|---|---|---|---|
| Hosted SaaS | Jina API | Per-query + per-GB indexed | Fast onboarding, no infra |
| Self-hosted | Local omni-small | One-time license + annual support | Data sovereignty, DPDP-safe |
| Embedded OEM | Either | Internal tooling pricing | Commerce Analytics Agent Builder first |

### Land-and-expand motion
- Land: text + Confluence/Notion (zero migration cost, immediate value)
- Expand: add Figma (image), then Loom (video) — each modality adds incremental value without rework
- Enterprise: ACL enforcement + DPDP compliance + SLA guarantees → premium tier

---

## D · Open Decisions Log

| ID | Decision | Options | Recommendation | Due |
|---|---|---|---|---|
| **D-01** | Commercial license path | A: Elastic Inference Service · B: Direct Jina AI agreement | **A** — faster, Elastic likely already in vendor stack | Sprint 0 🔴 |
| **D-02** | Model size default | small (1.74B, 8GB, 1024-dim) · nano (1.04B, 4GB, 768-dim) | **small** as default; nano as low-cost SKU. If precision delta < 3pp, default to nano. Needs spike. | Sprint 0 🔴 |
| **D-03** | PDF chunking strategy | A: Fixed 512-token · B: Page-level · C: Semantic sentence split | **B** (page-level) for PDFs — matches Jina native render. **A** for long Confluence pages. Needs spike. | Sprint 0 🔴 |
| **D-04** | Loom video embedding | A: 16 frames + audio (fused) · B: Thumbnail only · C: Full video (32 auto-frames) | **A** as default. **C** for async/high-accuracy path only. | Sprint 2 🟡 |
| **D-05** | Matryoshka dim default | 1024 (full) · 512 (2× saving) · 256 (4× saving) | **512** — MIEB-Lite shows < 2% nDCG drop vs. 1024. Validate on internal corpus. | Sprint 2 🟡 |
| **D-06** | ACL enforcement layer | A: Pre-filter metadata · B: Post-filter result set · C: ACL proxy sidecar | **A** — pre-filter is more secure; result set never leaks protected document metadata. **C** for large orgs. | Sprint 2 🟡 |
| **D-07** | Ingestion queue tech | A: Redis Streams · B: AWS SQS · C: In-process | **C** for MVP Sprint 1. **A** for production Sprint 3. Avoid SQS cloud lock-in. | Sprint 3 🟢 |

---

## S · Sprint Plan

### Sprint 0 · Weeks 1–2 — Spec Authoring & Decisions
**Deliverables**
- Resolve D-01, D-02, D-03 (all Sprint 0 blockers)
- D-02 spike: embed 500 Confluence pages with small vs. nano — measure Precision@5 delta
- D-03 spike: compare page-level vs. 512-token chunking on 50 PDF pages
- Draft Spec Sections 01–04 (Problem, Solution, Architecture, Data Model)
- Define golden eval dataset structure (50 text + 20 image query pairs)
- Schedule spec review at end of Sprint 0 before any code is written

**Gate:** License decision finalized · Spec Sections 01–04 reviewed and signed off

---

### Sprint 1 · Weeks 3–4 — Text-only MVP (Backward-Compat Proof)
**Deliverables**
- `EmbeddingBackend` abstract class + `JinaAPIBackend` + `LocalBackend`
- `get_backend(config)` factory, env var wiring
- Confluence connector — page fetch, markdown strip, 512-token chunking, enqueue
- Chroma collection setup — schema, HNSW config, metadata envelope
- `POST /search` — text query only, cosine ANN, `modality_filter`, `acl_groups` pre-filter
- Ingestion retry + dead-letter logic
- Eval run: Precision@5 ≥ 0.80 on Confluence golden set vs. BM25 baseline

**Gate:** Text search working · Backend switch proven via env var · Eval gate passed

---

### Sprint 2 · Weeks 5–6 — Image + PDF Modalities
**Deliverables**
- Figma connector — frame PNG export, resize, embed
- Notion connector — page → PDF export, Jina native render
- `/search` updated — `query_image_b64` input, modality/source filter params
- Resolve D-05 (Matryoshka dim) — benchmark 512 vs. 1024 on image retrieval corpus
- Resolve D-06 (ACL layer) — implement pre-filter metadata approach, write tests
- Eval run: MIEB-Lite nDCG@10 ≥ 0.70 · Figma→Confluence 20-pair golden set · p95 latency gate

**Gate:** Cross-modal text ↔ image search working · ACL enforcement verified · Latency SLA met

---

### Sprint 3 · Weeks 7–8 — Audio/Video + Production Hardening
**Deliverables**
- **Commercial license confirmed** — hard gate; no Sprint 3 code ships without it 🔴
- Loom connector — video → 16-frame extract + audio → fused embed (D-04: Option A)
- Redis Streams ingestion queue (replace in-process, D-07)
- `POST /ingest` webhook — real-time push from source connectors
- Optional re-ranker — cross-encoder on text snippet, `RERANK_ENABLED` toggle
- Load test: 100 concurrent queries · p95 all modalities within SLA (Locust)
- Docker Compose deployment manifest

**Gate:** Full omni-modal search live · All eval gates passed · Load test passed · License confirmed

---

## R · Risk Register

| ID | Risk | Impact | Probability | Mitigation |
|---|---|---|---|---|
| **RISK-01** 🔴 | License not cleared before GA | All commercial deployment blocked | Medium | Start D-01 Day 1. Elastic route is fastest. Internal tooling exempt — unblocks Sprint 1–2. |
| **RISK-02** 🟡 | Video embedding latency exceeds SLA | Loom connector unusable for realtime | Medium-high | Pre-extract 16 frames offline at ingestion time (D-04 Option A). Query uses pre-computed embedding — zero query-time overhead. |
| **RISK-03** 🟡 | Image retrieval accuracy below gate | Phase 2 (Sprint 2) delayed | Low | MIEB-Lite shows v5-omni-small at 0.73 nDCG@10. Run against internal Figma corpus early Sprint 2. Fall back to 1024-dim if 512 truncation causes regression. |
| **RISK-04** 🟡 | DPDP 2025 compliance gap | India data residency violation if PII flows to Jina API (non-India infra) | Medium | PII masking layer before Jina API calls. Self-hosted backend as default for sensitive content. Legal review of Stage 2 consent manager requirement. |
| **RISK-05** 🟢 | Chroma scalability ceiling | Index degradation beyond 500K docs | Low | HNSW scales well to 1M+. Monitor query latency at 500K threshold. Chroma Cloud or migration to Qdrant/Pinecone as contingency. |

---

## Quick-Start Reference

```python
from sentence_transformers import SentenceTransformer
from PIL import Image
import torch, chromadb

# Load model (local backend)
model = SentenceTransformer(
    "jinaai/jina-embeddings-v5-omni-small",
    trust_remote_code=True,
    model_kwargs={"default_task": "retrieval", "dtype": torch.bfloat16}
)

# Chroma collection
client = chromadb.PersistentClient(path="/data/chroma")
collection = client.get_or_create_collection(
    "multimodal-knowledge",
    metadata={"hnsw:space": "cosine"}
)

# Embed mixed batch
embeddings = model.encode([
    "How does the onboarding flow work?",   # text
    Image.open("figma-frame.png"),           # image
    "loom-recording.mp4"                     # video (pre-extracted frames)
])

# Matryoshka truncation to 512-dim
import torch.nn.functional as F
emb_512 = F.normalize(
    torch.tensor(embeddings)[:, :512], p=2, dim=1
).numpy()

# Query
results = collection.query(
    query_embeddings=[emb_512[0].tolist()],
    n_results=10,
    where={"acl_groups": {"$in": ["eng-all"]}}
)
```

---

*UC-1 · Enterprise Knowledge Search · Spec Plan v0.1 · May 2026*  
*jina-embeddings-v5-omni-{small,nano} · Chroma · FastAPI · arXiv:2605.08384*
