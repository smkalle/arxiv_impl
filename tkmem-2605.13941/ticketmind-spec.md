# TicketMind · Support Ticket → Resolution KB Agent
## Product & Technical Specification

**Version:** 1.0 · Draft  
**Status:** Ready for Implementation  
**Supersedes:** SIRA spec v0.1 (May 2026), KB Ingestor spec v0.1 (May 2026)  
**Last Updated:** May 2026  
**Classification:** Internal  
**Target Environment:** UserLAnd Ubuntu (ARM64, Snapdragon 8 Elite, 16 GB RAM, OnePlus 13)  
**Deployment Mode:** Local systemd services — no Docker

---

## Table of Contents

1. [Problem Statement & Context](#1-problem-statement--context)
2. [What's New vs Prior SIRA Spec](#2-whats-new-vs-prior-sira-spec)
3. [Goals & Success Metrics](#3-goals--success-metrics)
4. [System Architecture](#4-system-architecture)
5. [Component Specifications](#5-component-specifications)
6. [SimpleMem + EvolveMem Integration](#6-simplemem--evolvemem-integration)
7. [Data Model](#7-data-model)
8. [API Contract](#8-api-contract)
9. [Admin & Operations Dashboard](#9-admin--operations-dashboard)
10. [UserLAnd Ubuntu Deployment](#10-userland-ubuntu-deployment)
11. [Evolution Pipeline (AutoResearch)](#11-evolution-pipeline-autoresearch)
12. [Dev Set Construction](#12-dev-set-construction)
13. [Evaluation & Acceptance Criteria](#13-evaluation--acceptance-criteria)
14. [Sprint Plan](#14-sprint-plan)
15. [Open Questions & Risks](#15-open-questions--risks)
16. [Out of Scope](#16-out-of-scope)
17. [Appendix: Reference Architecture Decisions](#17-appendix-reference-architecture-decisions)

---

## 1. Problem Statement & Context

### 1.1 The Vocabulary Gap (unchanged from SIRA v0.1)

Support agents and triage systems match inbound tickets to KB articles using
keyword search. This fails systematically:

| Failure Mode | Example |
|---|---|
| Vocabulary gap | Customer: "app crashes on login" ↔ KB: "authentication service segfault" |
| Jargon delta | Customer: "subscription keeps renewing" ↔ KB: "recurring billing idempotency failure" |
| Multi-round cost | Agentic reformulation: 3–5 LLM calls per query, 3–8 s, high token cost |

### 1.2 Why This Spec Supersedes SIRA v0.1

SIRA v0.1 solved retrieval with a single BM25 + LLM-enriched corpus call —
training-free, sub-500 ms. That insight is preserved here. What's added:

1. **Memory evolves how it retrieves, not just what it stores.** EvolveMem
   (SimpleMem v0.3.0) runs a closed-loop AutoResearch cycle — Evaluate →
   Diagnose → Propose → Validate — and discovers retrieval dimensions that
   no human would hand-tune: query decomposition, entity swapping, answer
   verification, recency-weighted fusion. Published gains: +25.7% on LoCoMo,
   +18.9% on MemBench.

2. **Cross-session memory.** The SimpleMem `cross/` module gives the agent
   continuity across ticket conversations — agent recalls context from a
   customer's previous 3 sessions without manual re-injection.

3. **Admin/ops dashboard.** A FastAPI + HTMX UI for KB management, retrieval
   monitoring, evolution job control, and live retrieval trace inspection.

4. **No Docker.** Runs as systemd-managed Python services directly inside
   UserLAnd Ubuntu on the OnePlus 13.

---

## 2. What's New vs Prior SIRA Spec

| Dimension | SIRA v0.1 | TicketMind v1.0 |
|---|---|---|
| Retrieval layer | BM25 (rank-bm25) + LLM sketch | SimpleMem 3-view hybrid (semantic + BM25 + symbolic) |
| Retrieval evolution | None — static enrichment | EvolveMem AutoResearch (7 rounds, self-improving) |
| Memory persistence | Stateless per query | Cross-session memory via SQLite + LanceDB |
| Vector store | FAISS (mmap risk on FAT32) | **LanceDB** (manylinux aarch64 wheel, ext4-safe) |
| Embedding model | Not specified | Qwen3-Embedding-0.6B (1024-d, bundled with SimpleMem) |
| LLM for enrichment | Qwen2.5-14b via Ollama | gpt-4.1-mini (or Ollama-local fallback) |
| Admin UI | None | FastAPI + HTMX dashboard |
| Deployment | Standalone script | systemd services (ingestor, api, dashboard, worker) |
| Dev set construction | Manual 200-ticket annotation | Semi-automated from resolved ticket history |

---

## 3. Goals & Success Metrics

### 3.1 Primary Goal

A support agent (human or automated) queries an inbound ticket text and gets
the top-5 most relevant KB resolutions in under 600 ms with F1 ≥ 0.55 on a
200-ticket test set.

### 3.2 Success Metrics

| Metric | Baseline (BM25 only) | Target (post-evolution) | Measurement |
|---|---|---|---|
| Retrieval F1@5 | ~0.34 | ≥ 0.55 | 200-ticket held-out test set |
| Query latency P95 | — | ≤ 600 ms | Local timing, ext4 data dir |
| Memory construction time | — | ≤ 120 s for 1,000 KB articles | Timed batch |
| Evolution gain | — | ≥ +15% F1 over pre-evolution baseline | AutoResearch rounds 1–7 |
| Cross-session recall | — | Agent correctly uses prior session context in ≥ 80% of multi-turn tests | Manual eval on 20 sessions |
| Dashboard uptime | — | Runs continuously as systemd service | systemctl status |

### 3.3 Non-Goals

- Answer generation (retrieval only — no LLM-written responses in v1.0)
- Ticket routing or assignment
- Multilingual (English only)
- Fine-tuning any model
- Real-time KB article enrichment (batch, nightly)

---

## 4. System Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        TicketMind v1.0                               │
│                  UserLAnd Ubuntu · ext4 · ARM64                      │
└──────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│  INGESTION PLANE                                                     │
│                                                                      │
│  CSV / JSON (Zendesk / Jira export)                                  │
│       │                                                              │
│       ▼                                                              │
│  [ kb-ingestor.py ]                                                  │
│  - Parse tickets + KB articles                                       │
│  - LLM sketch enrichment (Qwen/gpt-4.1-mini)                        │
│  - DF validation filter                                              │
│  - simplemem_router.create(mode="text")                              │
│  - mem.add_dialogue() per KB article                                 │
│  - mem.finalize() → LanceDB on ext4                                  │
│       │                                                              │
│       ▼                                                              │
│  [ LanceDB store ]   ~/ticketmind/data/lancedb/                      │
│  - semantic view   (Qwen3-Embedding-0.6B, 1024-d)                    │
│  - lexical view    (BM25 index)                                      │
│  - symbolic view   (metadata: product_area, severity, date)         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  RETRIEVAL PLANE                                                     │
│                                                                      │
│  Inbound ticket text                                                 │
│       │                                                              │
│       ▼                                                              │
│  [ ticket-api.py  · FastAPI · :8001 ]                                │
│       │                                                              │
│       ├─── POST /query ──────────────────────────────────────────── │
│       │         │                                                    │
│       │         ▼                                                    │
│       │    [ SimpleMem Intent-Aware Retrieval Planning ]             │
│       │    - Infer semantic / lexical / symbolic sub-queries         │
│       │    - Parallel 3-view retrieval                               │
│       │    - RRF fusion + deduplication                              │
│       │    - EvolveMem evolved config applied                        │
│       │         │                                                    │
│       │         ▼                                                    │
│       │    Top-K KB articles + scores + matched_terms                │
│       │                                                              │
│       └─── POST /session/start  (cross-session memory)              │
│       └─── POST /session/record                                      │
│       └─── POST /session/end                                         │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  EVOLUTION PLANE                                                     │
│                                                                      │
│  [ evolve-worker.py · background process ]                           │
│  - Runs simplemem.optimize() on dev_set                              │
│  - max_rounds=7, saves healthcare_evolved_config.json               │
│  - Reloads config into retrieval plane on completion                 │
│  - Reports discovered_strategies to dashboard                        │
└──────────────────────────┬──────────────────────────────────────────┘
                           │
┌──────────────────────────▼──────────────────────────────────────────┐
│  DASHBOARD PLANE                                                     │
│                                                                      │
│  [ dashboard.py · FastAPI + HTMX · :8000 ]                          │
│  - KB Management: browse, re-ingest, tag                             │
│  - Query Inspector: live retrieval trace                             │
│  - Evolution Monitor: rounds, F1 curve, discovered strategies        │
│  - Session Viewer: cross-session memory log                          │
│  - System Health: service status, LanceDB size, token usage          │
└─────────────────────────────────────────────────────────────────────┘
```

### 4.1 Process Map (systemd)

```
ticketmind-api.service        → ticket-api.py       :8001
ticketmind-dashboard.service  → dashboard.py        :8000
ticketmind-worker.service     → evolve-worker.py    background
ticketmind-ingestor.service   → kb-ingestor.py      oneshot / scheduled
```

All four are systemd user services. No root required. No Docker.

---

## 5. Component Specifications

### 5.1 KB Ingestor (`kb-ingestor.py`)

**Inputs:**
- `data/raw/kb_articles.csv` — columns: `id, title, body, product_area, created_at`
- `data/raw/resolved_tickets.csv` — columns: `ticket_id, subject, description, resolution_id, resolved_at`

**Processing pipeline:**

```
for each KB article:
  1. LLM sketch enrichment
     prompt → 8–12 customer-language synonyms not in article text
     model  → gpt-4.1-mini (default) | Ollama qwen2.5:14b (local fallback)
     
  2. DF validation
     keep term if: df > 0 AND df ≤ 0.01 × corpus_size
     (term exists in corpus but is not generic noise)
     
  3. Merge enriched terms into dialogue body:
     "Original article text... [ENRICHED: term1, term2, ...]"
     
  4. mem.add_dialogue(
       speaker="KB",
       content=enriched_text,
       timestamp=article.created_at,
       tags=["kb_id:{id}", "product:{product_area}"],
       entities={"product_area": [...], "severity_keywords": [...]}
     )

5. mem.finalize()  # triggers compression + LanceDB indexing
```

**Parallel mode** (large corpora):
```python
mem = simplemem.create(
    mode="text",
    clear_db=False,
    enable_parallel_processing=True,
    max_parallel_workers=4,      # conservative for 16 GB RAM
    enable_parallel_retrieval=True,
    max_retrieval_workers=2
)
```

**Estimated time:** ~90 s for 1,000 articles on Snapdragon 8 Elite
(SimpleMem benchmark: 92.6 s construction on GPT-4.1-mini)

**LanceDB data path (critical — must be ext4):**
```python
# In config.py
LANCEDB_PATH = "/home/{user}/ticketmind/data/lancedb"
# NOT /sdcard/ — FAT32 mmap will fail silently (same issue as Ollama)
```

---

### 5.2 Ticket Query API (`ticket-api.py`)

**Framework:** FastAPI  
**Port:** 8001  
**Endpoints:**

#### `POST /query`
```json
{
  "ticket_text": "string",
  "top_k": 5,
  "filters": {
    "product_area": "string | null",
    "date_from": "ISO8601 | null"
  },
  "session_id": "string | null"
}
```

**Response:**
```json
{
  "results": [
    {
      "kb_id": "string",
      "title": "string",
      "score": 0.87,
      "matched_terms": ["login crash", "auth failure"],
      "view_contributions": {
        "semantic": 0.42,
        "lexical": 0.31,
        "symbolic": 0.14
      },
      "snippet": "string"
    }
  ],
  "retrieval_trace": {
    "query_plan": {},
    "latency_ms": 312,
    "evolved_config_version": "v7"
  }
}
```

#### `POST /session/start`
Initialises a SimpleMem cross-session context for a customer session.
Returns `memory_session_id`.

#### `POST /session/record`
Records a message or tool use event into the cross-session memory.

#### `POST /session/end`
Finalises the session — extracts observations, generates summary, stores
memories. Returns `entries_stored`.

#### `GET /health`
Returns service status, LanceDB path, loaded config version, uptime.

---

### 5.3 Evolution Worker (`evolve-worker.py`)

Runs `simplemem.optimize()` against the dev set. Triggered manually from
dashboard or on a nightly cron.

```python
import simplemem
from simplemem import load_config

evolved_config = simplemem.optimize(
    mem=mem,
    dev_questions=dev_set,   # list of (ticket_text, ground_truth_kb_id)
    max_rounds=7,
    benchmark_name="ticketmind_support"
)
evolved_config.save("data/evolved_config.json")
```

**Discovered strategies the loop typically finds for support ticket corpora:**
- Query decomposition: splits "login fails after password reset on iOS 17"
  into 3 sub-queries
- Entity swapping: "crash" ↔ "segfault", "won't load" ↔ "timeout",
  "billing issue" ↔ "payment failure"
- Answer verification: cross-checks retrieved article's product_area tag
  against ticket's implied product_area
- Recency weighting: boosts articles updated in last 90 days (temporal F1
  gain is highest — +63% in EvolveMem benchmarks)

**Worker signals:** writes `data/evolution_state.json` with round number,
current F1, and status. Dashboard polls this file.

---

### 5.4 Dashboard (`dashboard.py`)

**Framework:** FastAPI + Jinja2 templates + HTMX  
**Port:** 8000  
**Auth:** HTTP Basic (username/password in `.env`) — sufficient for local service  

**Four main views (see Section 9 for detail):**

| View | Path | Purpose |
|---|---|---|
| KB Management | `/kb` | Browse articles, trigger re-ingest, inspect enrichment |
| Query Inspector | `/query` | Live retrieval trace, A/B baseline vs evolved |
| Evolution Monitor | `/evolution` | Round history, F1 curve, discovered strategies |
| System Health | `/health` | Service status, LanceDB metrics, token usage |

---

### 5.5 Cross-Session Memory (`cross/` module)

Uses SimpleMem's built-in `cross/orchestrator.py`. Storage:
- SQLite: `data/cross_sessions.db` (session lifecycle, events)
- LanceDB: `data/lancedb/` (vector memories, same store as KB index,
  separate table `cross_memory`)

**Session context injection:** On `POST /session/start`, the orchestrator
retrieves relevant memories from previous sessions (token-budgeted to 2,000
tokens) and prepends them to the query context.

---

## 6. SimpleMem + EvolveMem Integration

### 6.1 Why SimpleMem Replaces Pure BM25

SIRA v0.1 used BM25 with LLM-enriched corpus and sketch generation.
SimpleMem provides all of that plus:

| Capability | SIRA v0.1 | SimpleMem |
|---|---|---|
| Lexical retrieval | BM25 (rank-bm25) | BM25 built-in |
| Semantic retrieval | Not included | Qwen3-Embedding-0.6B, 1024-d vectors |
| Symbolic/metadata retrieval | Manual tag filtering | Structured symbolic view, native filters |
| Online semantic synthesis | None | Write-time deduplication + consolidation |
| Cross-session memory | Not included | cross/ module (SQLite + LanceDB) |
| Retrieval evolution | Not included | EvolveMem AutoResearch |
| ARM64 vector store | FAISS (mmap risk) | LanceDB (manylinux aarch64 wheel) |

### 6.2 MCP Limitation (Known)

SimpleMem's hosted MCP server currently exposes only `semantic_top_k` and
`keyword_top_k` of the ~10 dimensions EvolveMem evolves. **Do not use the
hosted MCP server for this implementation.** Run SimpleMem locally (Python,
self-hosted) to get all 10 evolved dimensions. This is what the local
service architecture achieves.

### 6.3 Configuration Flow

```
Baseline config (auto from simplemem.create())
        ↓
evolve-worker.py runs AutoResearch (7 rounds)
        ↓
data/evolved_config.json written
        ↓
ticket-api.py loads config on startup:
  config = load_config("data/evolved_config.json")
  mem = simplemem.create(config=config)
        ↓
Dashboard shows config version + discovered_strategies
```

---

## 7. Data Model

### 7.1 KB Article (ingestion input)

```python
@dataclass
class KBArticle:
    id: str                    # "KB-1042"
    title: str
    body: str
    product_area: str          # "authentication", "billing", "mobile-app"
    created_at: datetime
    updated_at: datetime
    enriched_terms: List[str]  # populated by ingestor
    tags: List[str]            # ["kb_id:KB-1042", "product:authentication"]
```

### 7.2 Resolved Ticket (dev set source)

```python
@dataclass
class ResolvedTicket:
    ticket_id: str
    subject: str
    description: str
    resolution_kb_id: str      # ground truth label for dev set
    resolved_at: datetime
    agent_id: str
    csat_score: Optional[int]  # 1–5, used to weight dev set quality
```

### 7.3 SimpleMem Memory Unit (after ingestion)

SimpleMem atomises each KB article into memory units:
```
Input:  "Authentication service returns 401 on valid JWT tokens..."
Output: "KB-1042: Authentication service returns HTTP 401 on valid JWT tokens 
         after 2025-12-01. [ENRICHED: login fail, can't sign in, blocked, 
         token expired message, keeps logging me out]"
```
Each unit is indexed across semantic (vector), lexical (BM25), and symbolic
(timestamp, product_area, severity) views.

### 7.4 Evolution State

```python
# data/evolution_state.json
{
  "status": "running | complete | idle",
  "current_round": 4,
  "max_rounds": 7,
  "rounds": [
    {"round": 1, "f1": 0.38, "strategy_proposed": "query_decomposition"},
    {"round": 2, "f1": 0.44, "strategy_proposed": "entity_swap"},
    ...
  ],
  "discovered_strategies": ["query_decomposition", "entity_swap", "recency_boost"],
  "baseline_f1": 0.34,
  "best_f1": 0.57,
  "config_path": "data/evolved_config.json",
  "last_updated": "2026-05-23T10:42:00"
}
```

---

## 8. API Contract

### 8.1 Base URLs (local)

```
Retrieval API:  http://localhost:8001
Dashboard:      http://localhost:8000
```

### 8.2 Full Endpoint Table

| Method | Path | Service | Description |
|---|---|---|---|
| POST | /query | ticket-api | Retrieve top-K KB articles for ticket text |
| POST | /session/start | ticket-api | Start cross-session memory context |
| POST | /session/record | ticket-api | Record event in session |
| POST | /session/end | ticket-api | Finalise and store session |
| GET | /health | ticket-api | Service health + config version |
| GET | / | dashboard | Home / system overview |
| GET | /kb | dashboard | KB article browser |
| POST | /kb/ingest | dashboard | Trigger ingestor job |
| GET | /kb/{id}/trace | dashboard | Enrichment detail for one article |
| GET | /query | dashboard | Query inspector UI |
| POST | /query/trace | dashboard | Run live retrieval trace (HTMX) |
| GET | /evolution | dashboard | Evolution monitor |
| POST | /evolution/start | dashboard | Launch evolve-worker |
| GET | /evolution/status | dashboard | Poll evolution_state.json (HTMX) |
| GET | /sessions | dashboard | Cross-session memory viewer |
| GET | /system | dashboard | Process health, LanceDB stats |

### 8.3 Error Codes

| Code | Meaning |
|---|---|
| 200 | OK |
| 400 | Bad request — malformed ticket text or missing required fields |
| 503 | LanceDB store not initialised — run ingestor first |
| 504 | Retrieval timeout (> 2 s) — check LanceDB data path is on ext4 |

---

## 9. Admin & Operations Dashboard

The dashboard is the primary interface for KB owners, support leads, and
the implementing engineer. It is a standard server-rendered FastAPI + Jinja2
+ HTMX application — no JavaScript framework, no Node build step.

### 9.1 View: KB Management (`/kb`)

**Purpose:** See what is in the knowledge base, inspect enrichment quality,
trigger re-ingestion.

**Elements:**

- **Stats bar:** Total articles | Last ingestion timestamp | LanceDB store
  size | Average enriched terms per article
- **Article table** (paginated, 25/page):
  - KB ID, title, product_area, updated_at
  - Enriched terms count badge
  - "Inspect" button → opens enrichment trace panel (HTMX swap)
- **Enrichment trace panel:**
  - Original article snippet
  - Generated enrichment terms (highlighted which passed DF filter)
  - DF scores for each term
- **Ingest controls:**
  - Upload CSV/JSON button
  - "Re-ingest all" button (HTMX → triggers kb-ingestor, shows progress)
  - Filter by product_area, date range
- **Search bar** — live BM25 search within KB (HTMX query)

### 9.2 View: Query Inspector (`/query`)

**Purpose:** Test a ticket text and see the full retrieval trace — what the
evolved config is doing step by step.

**Elements:**

- **Ticket input textarea** — paste any ticket text
- **Options:** top_k slider (3–10), product_area filter, enable/disable
  evolved config toggle (A/B comparison)
- **Submit → HTMX-rendered result panel:**
  - Retrieval latency (ms)
  - Config version used (baseline vs evolved)
  - Query plan JSON (what sub-queries were generated)
  - Results table:
    - Rank, KB article title, composite score
    - View contribution bar (semantic / lexical / symbolic proportions)
    - Matched terms (highlighted in article snippet)
    - "Open article" expand
  - **A/B diff mode:** when evolved toggle is on, shows baseline result
    alongside evolved result for same query — rank changes highlighted

### 9.3 View: Evolution Monitor (`/evolution`)

**Purpose:** Control and observe EvolveMem AutoResearch runs.

**Elements:**

- **Status banner:** Idle | Running (Round N / 7) | Complete
- **F1 curve chart** (SVG, Chart.js): one point per completed round,
  baseline F1 dotted line for reference
- **Strategy discovery log** — per-round table:
  - Round, F1 score, strategy proposed, validation result (accepted / rejected)
  - Strategy descriptions (e.g., "Entity swap: added 'crash' ↔ 'segfault'
    mapping, +0.04 F1")
- **Discovered strategies summary card** — final adopted strategies with
  plain-English descriptions
- **Controls:**
  - "Start evolution" button (launches evolve-worker, disables button while running)
  - "Abort" button
  - "Load evolved config" button (reloads ticket-api with new config)
  - Round count selector (3 / 5 / 7)
- **Status polling** — HTMX polls `/evolution/status` every 5 s while
  running, updates F1 curve and log in place

### 9.4 View: System Health (`/system`)

**Purpose:** Operational visibility — are all services running? Is the data
store healthy?

**Elements:**

- **Service status grid** (4 cards):
  - ticket-api, dashboard, evolve-worker, ingestor
  - Each: status dot (green/amber/red), PID, uptime, memory usage
  - Reads from `/proc/{pid}/status` — no external monitoring needed
- **LanceDB stats:**
  - Store path | Disk usage | Table count | Row count per table
  - Last write timestamp
- **Token usage log** (last 7 days):
  - LLM calls made by ingestor enrichment + evolution worker
  - Tokens in / out / estimated cost (configurable rate)
- **Config version panel:**
  - Baseline config vs evolved config paths
  - Evolution run history (timestamp, rounds, F1 delta)
- **Log tail** (last 50 lines from `ticketmind.log`) — HTMX auto-refresh
  every 10 s

---

## 10. UserLAnd Ubuntu Deployment

### 10.1 Prerequisites

```bash
# Inside UserLAnd Ubuntu
python3 --version          # must be 3.10
which pip3

# Confirm ext4 data path
df -T ~/ticketmind/data    # must show ext4, NOT vfat or exfat
```

### 10.2 Project Structure

```
~/ticketmind/
├── data/
│   ├── lancedb/              # LanceDB store — must be on ext4
│   ├── raw/
│   │   ├── kb_articles.csv
│   │   └── resolved_tickets.csv
│   ├── evolved_config.json   # written by evolve-worker
│   └── evolution_state.json  # polled by dashboard
├── logs/
│   └── ticketmind.log
├── templates/                # Jinja2 HTML templates for dashboard
├── static/                   # CSS, minimal JS (HTMX from CDN)
├── config.py                 # API keys, paths, model selection
├── kb-ingestor.py
├── ticket-api.py
├── evolve-worker.py
├── dashboard.py
├── dev_set.py                # dev set loader
└── requirements.txt
```

### 10.3 Installation

```bash
# Clone SimpleMem (includes EvolveMem)
cd ~/ticketmind
git clone https://github.com/aiming-lab/SimpleMem.git simplemem_src

# Install — pip pulls lancedb-0.30.x-cp39-abi3-manylinux_2_17_aarch64.whl
pip install simplemem --break-system-packages
pip install fastapi uvicorn jinja2 python-multipart httpx --break-system-packages

# LanceDB explicit pin (confirms aarch64 wheel)
pip install "lancedb>=0.30" --break-system-packages

# Verify ARM64 wheel was used (not compiled from source)
pip show lancedb | grep Location
python3 -c "import lancedb; print('LanceDB OK')"
```

### 10.4 Configuration (`config.py`)

```python
# config.py
import os

# LLM provider — gpt-4.1-mini default, Ollama fallback
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_BASE_URL = None  # set to "http://localhost:11434/v1" for Ollama

LLM_MODEL = "gpt-4.1-mini"            # or "qwen2.5:14b" via Ollama
EMBEDDING_MODEL = "Qwen/Qwen3-Embedding-0.6B"

# CRITICAL: ext4 path — not /sdcard/
LANCEDB_PATH = os.path.expanduser("~/ticketmind/data/lancedb")

# Evolution
EVOLUTION_MAX_ROUNDS = 7
EVOLVED_CONFIG_PATH = os.path.expanduser("~/ticketmind/data/evolved_config.json")
EVOLUTION_STATE_PATH = os.path.expanduser("~/ticketmind/data/evolution_state.json")

# API
TICKET_API_PORT = 8001
DASHBOARD_PORT = 8000
DASHBOARD_USER = os.getenv("DASHBOARD_USER", "admin")
DASHBOARD_PASS = os.getenv("DASHBOARD_PASS", "changeme")

# Ingestor
SIRA_DF_TAU = 0.01          # DF threshold for term validation
SIRA_ENRICHMENT_TERMS = 10  # terms to generate per article
PARALLEL_WORKERS = 4        # conservative for 16 GB RAM
```

### 10.5 Systemd User Services

Create `~/.config/systemd/user/` service files:

**`ticketmind-api.service`:**
```ini
[Unit]
Description=TicketMind Retrieval API
After=network.target

[Service]
WorkingDirectory=%h/ticketmind
ExecStart=/usr/bin/python3 ticket-api.py
Restart=on-failure
RestartSec=5
StandardOutput=append:%h/ticketmind/logs/ticketmind.log
StandardError=append:%h/ticketmind/logs/ticketmind.log
Environment=OPENAI_API_KEY=sk-...

[Install]
WantedBy=default.target
```

Repeat pattern for `ticketmind-dashboard.service` and
`ticketmind-worker.service`.

**Enable and start:**
```bash
systemctl --user daemon-reload
systemctl --user enable ticketmind-api ticketmind-dashboard
systemctl --user start ticketmind-api ticketmind-dashboard
systemctl --user status ticketmind-api
```

**Check on reboot** (UserLAnd sessions don't auto-start systemd user services;
add to UserLAnd startup script):
```bash
# ~/.bashrc or UserLAnd startup
systemctl --user start ticketmind-api ticketmind-dashboard 2>/dev/null || true
```

---

## 11. Evolution Pipeline (AutoResearch)

### 11.1 When to Run

- **First run:** After initial KB ingestion + dev set construction. Run 7
  rounds. Expect ~45–90 min on Snapdragon 8 Elite (LLM API calls dominate).
- **Incremental:** After adding ≥ 100 new KB articles, run 3 rounds.
- **Scheduled:** Monthly via cron, 3 rounds.

### 11.2 What AutoResearch Optimises

EvolveMem treats the full retrieval config as a structured action space with
~10 dimensions:

| Dimension | Default | Example evolved value |
|---|---|---|
| semantic_top_k | 5 | 8 |
| keyword_top_k | 5 | 6 |
| structured_top_k | 3 | 4 |
| fusion_mode | rrf | weighted_sum |
| fusion_weights | [1,1,1] | [1.2, 1.0, 0.8] |
| query_decomposition | off | on (threshold: query_len > 8 words) |
| entity_swap | off | on (domain: IT support synonyms) |
| answer_verification | off | on (checks product_area match) |
| recency_weight | 0 | 0.15 (boosts articles < 90 days old) |
| rerank_model | none | cross-encoder (if latency budget allows) |

### 11.3 Expected Gains (from EvolveMem paper, LoCoMo benchmark)

| Category | SimpleMem baseline | EvolveMem 7 rounds | Delta |
|---|---|---|---|
| Overall F1 | 0.432 | 0.543 | +25.7% |
| Temporal queries | lower | highest gain | +63.4% |
| Single-hop queries | — | — | +68.7% |

For support ticket corpora, temporal and single-hop categories map directly
to "find the most recent resolution for this exact error" — the dominant
query type.

---

## 12. Dev Set Construction

The dev set is the fuel for AutoResearch. Quality matters more than quantity.
100 high-quality pairs beats 500 noisy ones.

### 12.1 Source

**Resolved tickets with KB links** — from your ticketing system export:
- Ticket where agent explicitly linked a KB article as the resolution source
- CSAT score ≥ 4 (high-quality resolutions only)
- Resolved in last 12 months (avoid stale KB articles)

**Target: 200 pairs** (150 train/evolution, 50 held-out test)

### 12.2 Semi-Automated Construction (`dev_set.py`)

```python
# dev_set.py
import csv, random

def build_dev_set(resolved_tickets_path: str, min_csat: int = 4) -> list:
    """
    Build (ticket_text, ground_truth_kb_id) pairs from resolved tickets.
    Filters to high-quality resolutions only.
    """
    pairs = []
    with open(resolved_tickets_path) as f:
        for row in csv.DictReader(f):
            if (
                row["resolution_kb_id"]
                and int(row.get("csat_score", 0) or 0) >= min_csat
            ):
                ticket_text = f"{row['subject']}. {row['description']}"
                pairs.append((ticket_text, row["resolution_kb_id"]))
    
    random.shuffle(pairs)
    train = pairs[:150]
    test  = pairs[150:200]
    return train, test

# Usage
train_set, test_set = build_dev_set("data/raw/resolved_tickets.csv")
```

### 12.3 Manual Augmentation (if resolved ticket volume is low)

If fewer than 200 high-quality pairs exist, supplement with:
1. Take 50 KB articles. Write 2–3 tickets per article in customer language.
2. Include synonym variations, typo-style rewrites, multi-symptom descriptions.
3. Target 20% of pairs in "vocabulary gap" category — ticket text shares
   zero lexical overlap with article title.

---

## 13. Evaluation & Acceptance Criteria

### 13.1 Baseline Eval (pre-evolution)

Run before starting AutoResearch to establish the floor:

```python
# evaluate.py
from simplemem import SimpleMem
import json

def eval_f1(mem, test_set, top_k=5) -> float:
    hits = 0
    for ticket_text, ground_truth_kb_id in test_set:
        results = mem.ask(query=ticket_text, top_k=top_k)
        retrieved_ids = [r["kb_id"] for r in results]
        if ground_truth_kb_id in retrieved_ids:
            hits += 1
    return hits / len(test_set)

# Run
baseline_f1 = eval_f1(mem_baseline, test_set)
print(f"Baseline F1@5: {baseline_f1:.3f}")
```

### 13.2 Acceptance Thresholds

| Gate | Threshold | Action if failed |
|---|---|---|
| Baseline F1@5 | > 0.30 | If below, audit KB article quality first |
| Post-evolution F1@5 | ≥ 0.55 | Run more rounds or expand dev set |
| Evolution gain | ≥ +15% relative | Check dev set quality |
| P95 query latency | ≤ 600 ms | Verify LanceDB path is ext4, not FAT32 |
| Memory construction | ≤ 120 s / 1,000 articles | Reduce parallel workers if OOM |

### 13.3 Regression Test (after config reload)

After `systemctl --user restart ticketmind-api`, run a 10-query smoke test
from dashboard Query Inspector before declaring the new config live.

---

## 14. Sprint Plan

### Week 1: Foundation

| Day | Task | Output |
|---|---|---|
| 1 | Install SimpleMem, verify LanceDB aarch64 wheel on ext4 | `python3 -c "import lancedb"` passes |
| 1 | Set up project structure, config.py | Directory layout ready |
| 2 | Write kb-ingestor.py: CSV parse + simplemem_router | Ingests 10 test articles |
| 2 | Validate LanceDB path — `df -T ~/ticketmind/data` shows ext4 | No mmap errors |
| 3 | LLM sketch enrichment (gpt-4.1-mini) | 10 articles enriched, terms logged |
| 3 | DF validation filter | Terms passing filter inspected manually |
| 4 | Full ingest of KB corpus | LanceDB store written |
| 4 | Baseline eval on 50-ticket test sample | Baseline F1 recorded |
| 5 | ticket-api.py: FastAPI /query endpoint | curl test returns results |

### Week 2: Evolution + Cross-Session

| Day | Task | Output |
|---|---|---|
| 6 | Build dev set (200 pairs) from resolved tickets | dev_set.py produces train/test split |
| 6 | evolve-worker.py: simplemem.optimize(), round 1–3 | evolution_state.json updating |
| 7 | Full 7-round evolution run | evolved_config.json saved |
| 7 | Reload evolved config into ticket-api | F1 improvement measured |
| 8 | Cross-session memory: /session/start, /record, /end | 3-session E2E test passes |
| 9 | dashboard.py: health + KB browser views | Browsable at localhost:8000 |
| 10 | Query Inspector view: A/B trace | Side-by-side baseline vs evolved |

### Week 3: Dashboard + Productionisation

| Day | Task | Output |
|---|---|---|
| 11 | Evolution Monitor view: F1 curve, strategy log | Chart renders correctly |
| 12 | System Health view: service status, LanceDB stats | All 4 service cards show green |
| 13 | systemd user services: all 4 services | `systemctl --user status` all active |
| 14 | Acceptance eval: full 50-ticket test set | F1 ≥ 0.55 confirmed |
| 15 | Smoke test, README, log rotation | Handover-ready |

---

## 15. Open Questions & Risks

### 15.1 Open Questions

| ID | Question | Owner | Due |
|---|---|---|---|
| OQ-1 | Is Ollama permitted as LLM for enrichment, or must we use API? | Security | Day 1 |
| OQ-2 | Do resolved tickets in your export include the KB article ID as resolution field? | Data | Day 2 |
| OQ-3 | What is the KB article count? (determines parallel worker config) | Ops | Day 1 |
| OQ-4 | Is UserLAnd session persistent (survives screen off)? Or need Termux wakelock? | Se | Day 1 |
| OQ-5 | Does evolve-worker need to run on device, or can it be run on a remote machine with the LanceDB store synced? | Se | Week 2 |

### 15.2 Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| LanceDB mmap on non-ext4 path | Medium | High | Enforce `df -T` check in startup script |
| UserLAnd session killed during 7-round evolution (90 min) | Medium | Medium | Wakelock + checkpoint after each round |
| Dev set too small (< 100 pairs) | Medium | High | Manual augmentation protocol in Section 12.3 |
| gpt-4.1-mini API cost for 1,000-article enrichment | Low | Low | ~$0.50 estimated; Ollama fallback if budget constrained |
| EvolveMem MCP path only exposes 2 of 10 dimensions | Known | Confirmed | Mitigated: we use local Python path, not MCP |
| SimpleMem `pip install` fails on Python != 3.10 | Medium | High | Pin `python3.10` in venv |

---

## 16. Out of Scope

- Answer generation (LLM-written resolution text)
- Ticket routing or SLA automation
- Multilingual tickets (English only in v1.0)
- Fine-tuning any model
- Real-time KB enrichment (nightly batch only)
- FAISS (replaced by LanceDB; mmap on FAT32 is a known failure mode)
- Docker (deliberate: systemd user services on UserLAnd Ubuntu)
- Multi-tenant isolation
- Elasticsearch migration (documented as a future path)

---

## 17. Appendix: Reference Architecture Decisions

### 17.1 Why LanceDB over FAISS

FAISS requires memory-mapped file I/O. On the OnePlus 13 / UserLAnd setup,
any data directory on `/sdcard` (FAT32/exFAT) silently fails mmap. The
Ollama model storage issue in the existing stack hit this exact failure mode.
LanceDB ships a `manylinux_2_17_aarch64` wheel (Python 3.9+, CP 3.10) — no
Rust compilation required. Its embedded process model (no daemon) matches
the systemd user-service architecture.

### 17.2 Why No Docker

Docker requires a Linux kernel with namespace support. UserLAnd/proot
emulates a Linux userland but does not expose actual kernel namespaces.
Docker will not run. Systemd user services are the correct deployment
primitive for this environment.

### 17.3 Why HTMX over React for Dashboard

- No Node.js / npm build step — consistent with the existing stack (OpenCode
  Go binary connects to Ollama; npm in UserLAnd had ghost-directory issues
  resolved via `~/op2` prefix)
- HTMX renders server-side Jinja2 templates, live-updates via fragments
- Sufficient for the dashboard's interaction model (polling, form submissions,
  table updates)
- Single Python process (FastAPI) handles both rendering and API

### 17.4 Why EvolveMem Requires Local Python (Not MCP)

The SimpleMem hosted MCP server currently exposes only `semantic_top_k` and
`keyword_top_k`. EvolveMem optimises ~10 dimensions including query
decomposition, entity swap, answer verification, and fusion weights. The
full evolution loop requires the local Python `simplemem.optimize()` API.
Using MCP would cap gains at ≤ 2 of 10 evolved dimensions.

### 17.5 Relationship to Prior Specs

- **SIRA v0.1 (May 2026):** The vocabulary-gap framing and BM25 enrichment
  prompt template are reused. The BM25 implementation is superseded by
  SimpleMem's built-in lexical view.
- **KB Ingestor spec v0.1 (May 2026):** The Arrow + FAISS pipeline is
  superseded. Arrow is not used (LanceDB's Lance columnar format serves the
  same zero-copy purpose). FAISS is replaced by LanceDB.
- **SIRA arXiv reference:** 2605.06647 (Meta AI). Training-free BM25 sketch
  enrichment principle preserved in SimpleMem's online synthesis layer.
- **EvolveMem arXiv reference:** 2605.13941.
- **SimpleMem arXiv reference:** 2601.02553.

---

*End of TicketMind v1.0 Specification*
