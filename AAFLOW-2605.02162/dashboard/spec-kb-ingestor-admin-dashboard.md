# Technical Product Spec: KB Ingestor — Admin & Ops Dashboard

**Product:** `kb-ingestor-admin` v0.1.0  
**Status:** Draft — Ready for Engineering Review  
**Author:** AI Product  
**Last Updated:** 2026-05-12  
**Depends On:** `kb-ingestor` v0.1.0 (spec: `spec-kb-ingestor.md`)  
**Feeds:** SIRA Support Ticket → Resolution KB Prototype (upstream index health visibility)

---

## Table of Contents

1. [Problem Statement](#1-problem-statement)
2. [Goals & Non-Goals](#2-goals--non-goals)
3. [User Personas & Roles](#3-user-personas--roles)
4. [Design North Star](#4-design-north-star)
5. [Feature Regions](#5-feature-regions)
6. [Screen Inventory & Navigation](#6-screen-inventory--navigation)
7. [API Contract](#7-api-contract)
8. [Data Model — SQLite Schema](#8-data-model--sqlite-schema)
9. [Real-time Layer](#9-real-time-layer)
10. [Component Inventory](#10-component-inventory)
11. [Role Access Matrix](#11-role-access-matrix)
12. [Performance Requirements](#12-performance-requirements)
13. [Error Handling](#13-error-handling)
14. [Testing Plan](#14-testing-plan)
15. [Build Roadmap](#15-build-roadmap)
16. [Open Questions](#16-open-questions)
17. [Appendix: Dependency Stack](#17-appendix-dependency-stack)

---

## 1. Problem Statement

### Context

`kb-ingestor` ships as a CLI tool and Python library. Ops teams running daily ingestion cycles on Zendesk/Jira exports currently have no visibility into pipeline health without SSH access and manual log inspection. There is no way to:

- Know which operator stage (OP-1 through OP-4) is the bottleneck on a given run.
- Identify which specific batch IDs failed without reading `failed_rows.json` from disk.
- Trigger a targeted retry of failed batches without re-running the full pipeline.
- Track the Arrow vs baseline speedup trend across runs to validate the AAFLOW performance claim over time.

### Pain Points

| Pain | Current State | Impact |
|---|---|---|
| No run visibility | Ops reads stdout logs from CLI | Slow incident diagnosis; no batch-level detail |
| No retry without full re-run | Failed batches require CLI re-run of full source file | Wasted compute; index freshness lag |
| No index health signal | FAISS file checked manually | Dim mismatch discovered only when SIRA query fails |
| No speedup tracking | Benchmark run manually, not persisted | Can't prove or defend the Arrow performance gain over time |
| No operator separation | Full CLI access or no access | Ops engineers need limited retry access, not full config access |

### Hypothesis

A purpose-built admin and ops console — backed by a SQLite run metadata store and a FastAPI wrapper over the kb-ingestor Python API — will reduce mean-time-to-diagnose a failed ingestion run from ~15 minutes (log inspection) to under 90 seconds, while giving admin users full pipeline configuration control from a browser.

---

## 2. Goals & Non-Goals

### Goals

- **G1** — Give ops engineers a live view of active run progress at per-stage (OP-1 → OP-4) and per-batch granularity, streamed in real time via SSE without page reload.
- **G2** — Enable targeted retry of failed batch IDs from the UI without requiring full pipeline re-run or CLI access.
- **G3** — Provide admin users a 5-step New Ingestion Wizard to configure, validate, and trigger ingestion runs entirely from the browser.
- **G4** — Persist all run metadata, stage timings, batch statuses, and error details in SQLite so ops can query historical runs and track speedup trends.
- **G5** — Enforce role-based access (Admin, Ops, Read-only) at the API layer — not just in the UI.
- **G6** — Surface index health (doc count, embedding dim, last-updated, Arrow IPC ↔ FAISS ID consistency) without requiring direct file system access.

### Non-Goals

- Not a search or query interface — SIRA owns the KB query UI.
- Not a ticket viewer — raw ticket content is never displayed in this dashboard.
- Not a multi-tenant system — single-deployment, single-team scope in v0.1.
- No Postgres migration path in v0.1 — SQLite is the permanent store for this scale.
- No mobile-optimised layout — ops console targets desktop browsers (min-width 1280px).
- No Zendesk/Jira live API integration — source inputs are uploaded files only (v0.1).
- No separate real-time infrastructure — FastAPI native `StreamingResponse` handles SSE.

---

## 3. User Personas & Roles

### Admin

Full access. Owns the pipeline.

- Configures new ingestion pipelines (source mapping, embed model, batch params, null policy).
- Manages saved configurations and credentials for source connectors.
- Schedules recurring ingestion runs (v0.2).
- Triggers new runs and full re-runs.
- Retires / archives indexes with confirmation guard.
- Configures alert rules and notification channels (v0.2).
- Full audit log access.

### Ops / On-call

Incident responder. Read + Retry access.

- Monitors live run status and per-stage latency.
- Reads batch-level error details and downloads `failed_rows.json`.
- Triggers targeted retry on specific failed batch IDs.
- Views index health, artifact metadata, and run history.
- Cannot modify configuration, credentials, schedules, or delete indexes.

### Read-only / Auditor

Compliance and review access.

- Views run history and run detail (no error stack traces).
- Views index registry (no artifact downloads).
- Views audit log.
- No write access of any kind.

---

## 4. Design North Star

> An ops engineer receives a failure alert, opens the dashboard, identifies the failing batch ID and error class, and triggers a targeted retry — **in under 90 seconds** — without SSH access, log files, or CLI commands.

Every screen and interaction is tested against this constraint. Features that don't contribute to it are deferred.

### Core UX Principles

**Observability maps 1:1 to the operator DAG.** Every metric, chart, and alert is scoped to OP-1 through OP-4. There is no aggregate "pipeline health" score. Operators are the atomic unit of visibility.

**Errors surface at the closest point to failure.** Batch-level errors appear on the batch row, not just the run header. Error class, human message, affected row count, and a copy-JSON action are always co-located.

**URL-based state for all filters and drill-downs.** Ops engineers paste deep links into incident tickets. `/runs?status=failed&date=2026-05-11` and `/runs/0047/batches/12` must be stable, bookmarkable URLs.

**Role permissions enforced at the API layer.** The UI may hide buttons, but the backend rejects unauthorised actions with `403`. UI-only role enforcement is not sufficient.

---

## 5. Feature Regions

### Region 1 — Run Dashboard (Home) · `v0.1`

The default landing screen for both Admin and Ops.

**KPI Strip (top of page):**

| Metric | Data Source | Update Frequency |
|---|---|---|
| Active runs | `runs` table, `status = 'running'` count | SSE / 5s poll |
| Tickets indexed today | `runs` aggregate, `completed_at` = today | SSE on run complete |
| Last run status | Latest row in `runs` | SSE on status change |
| Index size (MB) | `indexes` table, `size_bytes` | On index update |
| Speedup vs baseline | Latest `run_summary.speedup_x` | On run complete |

**Throughput Sparkline:** tickets/sec over the last 30 minutes from `run_events` table, rendered as a 120×40px miniature SVG line chart. No axis labels — relative pattern only. Auto-updates via SSE.

**Active Run Progress Bar:** Per-stage segment bar (OP-1 → OP-4). Each segment: idle (gray) / active (teal animated) / done (green) / failed (red). Stage label and elapsed time shown below each segment. Live-updated via SSE deltas.

**Recent Runs Table:** Columns: Run ID · Source filename · Status badge · Rows · Elapsed · Speedup · Index name · Actions. Default sort: newest first. Filterable by status, date range, source type. Row click navigates to Run Detail. Actions: View detail (all roles), Retry failed batches (Admin + Ops), Re-run (Admin only).

**Quick Actions:** "Trigger New Ingestion" (Admin only) — navigates to Wizard. "View Last Failed Run" (all roles) — jumps to the most recent failed run detail.

---

### Region 2 — Run Detail & Batch Inspector · `v0.1`

Drill-down screen for a single run. Route: `/runs/{run_id}`.

**Run Header:** Run ID, source filename, status badge, start time, elapsed, rows processed / total, success rate percentage.

**Stage Timeline:** Horizontal bar chart of per-stage wall times (t_load, t_preprocess, t_embed, t_upsert). Bars are proportional to elapsed time within the run total. Hover tooltip: exact milliseconds + row count processed at each stage. Failed stages rendered in red.

**Batch Status Grid:** One cell per batch. Color: green (done), teal (running), amber (queued), red (failed), gray (not started). Renders up to 256 batches without scroll. Click a cell to jump to the batch detail panel below.

**Batch Detail Panel:** Appears below the grid when a batch cell is clicked. Shows: Batch ID, rows, status, embed duration, error class (if failed), human error message, affected row IDs (up to 10 shown, "download all" for the rest). Copy-JSON button: copies full error details + run ID + timestamp as a single JSON object for pasting into incident tickets.

**Download Actions (Ops + Admin):**
- `run_summary.json` — full run metadata
- `failed_rows.json` — all failed row IDs across all batches
- Benchmark report (Markdown) — if benchmark was run alongside ingest

**Retry Actions:**
- "Retry failed batches" — triggers `/runs/{id}/retry` with the failed batch IDs pre-filled. Available to Admin and Ops. Disabled with explanatory text if the run is still active.
- "Full re-run" — triggers a new run with the identical configuration. Admin only. Requires confirmation modal.

**Serialization Overhead Chart:** Side-by-side bar chart: Arrow pipeline total vs Pandas baseline estimate (calculated from benchmark data). Labeled with speedup multiplier. Present on every completed run.

---

### Region 3 — New Ingestion Wizard · `v0.1`

Full-page 5-step form. Route: `/runs/new`. Admin only.

The wizard persists the user's last-used configuration per step in `localStorage` so repeat runs require minimal changes.

**Step 1 — Source**

- Upload CSV or JSON file (drag-and-drop + file picker). Max file size: 500MB.
- Or: select a previously uploaded source from a saved-sources dropdown (shows filename, upload date, row count).
- Source type auto-detected from extension; manual override available.
- Instant row count preview on upload (Arrow reader, no embedding).

**Step 2 — Configuration**

| Field | Default | Constraint |
|---|---|---|
| Batch size | 128 | 16 – 512 |
| Max workers | 4 | 1 – 16 |
| Max chunk chars | 512 | 64 – 2048 |
| Min chunk chars | 20 | 5 – 256 |
| Null policy | drop | drop / raise |

All fields show their effect inline (e.g., "At batch_size=128 with 10,000 rows: ~79 batches").

**Step 3 — Model**

- Embed model selector: shows model name, dim, approx. RAM requirement, and a "last used in run-XXXX" tag.
- Default: `all-MiniLM-L6-v2` (384-dim, ~90MB RAM).
- Warning shown if selected model dim differs from the target index's current dim (would trigger `EmbedDimMismatchError` on append).

**Step 4 — Output**

- Target index name: text input with existing index names shown as suggestions.
- Append vs Overwrite toggle. Append shows current index doc count + new row count = estimated total.
- Output path: pre-filled from server config; editable by admin.

**Step 5 — Review & Pre-flight**

- Summary of all config from steps 1–4 as a read-only table.
- Diff from last run config: changed fields highlighted in amber.
- "Run Schema Validation" button: calls `/runs/{id}/validate` — validates source schema without embedding. Shows missing columns, null counts, detected source type. Must pass before the "Start Ingestion" button is enabled.
- "Estimate run time" button: calls `/runs/estimate` — returns projected elapsed based on row count, batch size, and historical throughput for the selected model.
- "Start Ingestion" primary button: triggers the run and navigates to the new run's detail page.

---

### Region 4 — Index Health · `v0.1`

Route: `/indexes`. Visible to all roles; write actions Admin only.

**Index Registry Table:** Columns: Index name · Doc count · Embedding dim · Last updated · Size on disk · Consistency status · Actions.

**Consistency Status indicator:** Green checkmark if `faiss_id` max in Arrow IPC = `index.ntotal`. Red warning if mismatch detected. Gray dash if consistency check has not been run yet.

**Index History:** Click an index name to expand a sub-table of all ingestion runs that contributed to it, with row counts and timestamps.

**Artifact Downloads (Admin + Ops):** Per-index buttons: Download `tickets.arrow` · Download `index.faiss` · Download `run_summary.json`. All served via signed URL from `/indexes/{name}/artifacts`.

**Retire / Archive (Admin only):** Soft-delete with a 30-second undo window. Confirmation modal requires typing the index name. Audit log entry written on confirm.

---

### Region 5 — Scheduler · `v0.2`

Route: `/schedules`. Admin only.

- Create, edit, pause, delete scheduled ingestion jobs.
- Schedule input: cron expression or plain-language picker ("Every day at 02:00 IST").
- Human-readable schedule preview and next-3-runs countdown.
- Overlap guard: blocks new run if previous scheduled run is still active. Configurable: skip or queue.
- Last-run status badge on each schedule row.

---

### Region 6 — Alerts & Notifications · `v0.2`

Route: `/alerts`. Admin config; Ops view-only.

- Alert rule builder: metric / comparator / threshold (e.g., `speedup_x < 2.0`, `batch_success_rate < 0.9`).
- Channels: email (SMTP), Slack webhook, PagerDuty integration key.
- Alert history log: fired / resolved / silenced.
- Silence windows with start/end timestamps for planned maintenance.
- Test-fire button before saving a rule.

---

## 6. Screen Inventory & Navigation

### Route Map

```
/                          → Run Dashboard (Home)
/runs                      → Run history list (filterable)
/runs/new                  → New Ingestion Wizard (Admin only)
/runs/{run_id}             → Run Detail & Batch Inspector
/runs/{run_id}/batches/{batch_id}  → Batch detail anchor (same page, scrolled)
/indexes                   → Index Health registry
/indexes/{name}            → Single index detail + history
/schedules                 → Scheduler (v0.2, Admin only)
/alerts                    → Alert rules (v0.2)
/settings                  → App config: server URL, model cache path (Admin only)
/audit                     → Audit log (Admin + Read-only)
```

### Navigation Structure

Left sidebar, sticky. Two sections:

**Monitor** (all roles): Dashboard · Runs · Indexes  
**Manage** (Admin only, grayed for others): New Ingestion · Schedules · Alerts · Settings

Active item indicated by left border accent + background tint. Role-restricted items are visible but disabled with a tooltip ("Requires Admin role") — not hidden. Hidden navigation creates confusion for ops when roles change.

---

## 7. API Contract

All endpoints are served by a FastAPI application that wraps the `kb-ingestor` Python API. The dashboard frontend calls only these endpoints — it never reads Arrow IPC or FAISS files directly. Authentication: JWT tokens, role claim in payload.

### Runs

| Method | Endpoint | Role | Description |
|---|---|---|---|
| `GET` | `/api/runs` | All | Paginated run history. Query params: `status`, `source_type`, `date_from`, `date_to`, `page`, `limit` |
| `POST` | `/api/runs` | Admin | Trigger new ingestion run. Body: `IngestConfig` JSON |
| `GET` | `/api/runs/{run_id}` | All | Full run detail: header, stage timings, batch table |
| `GET` | `/api/runs/{run_id}/stream` | All | SSE stream of live stage + batch status deltas for an active run |
| `POST` | `/api/runs/{run_id}/retry` | Admin, Ops | Retry specific batch IDs. Body: `{ "batch_ids": ["batch-12", ...] }` |
| `POST` | `/api/runs/{run_id}/retry-all-failed` | Admin, Ops | Retry all failed batches in a run (convenience shortcut) |
| `POST` | `/api/runs/validate` | Admin | Pre-flight schema validation. Body: multipart file upload. Returns schema report, null counts, detected source type |
| `POST` | `/api/runs/estimate` | Admin | Estimate run time. Body: `{ "row_count": N, "batch_size": N, "embed_model": "..." }`. Returns `{ "estimated_seconds": N, "p50_throughput": N }` based on historical run data |
| `GET` | `/api/runs/{run_id}/artifacts/summary` | Admin, Ops | Download `run_summary.json` |
| `GET` | `/api/runs/{run_id}/artifacts/failed-rows` | Admin, Ops | Download `failed_rows.json` |

### Indexes

| Method | Endpoint | Role | Description |
|---|---|---|---|
| `GET` | `/api/indexes` | All | Registry: name, doc_count, embed_dim, last_updated, size_bytes, consistency_status |
| `GET` | `/api/indexes/{name}` | All | Single index detail + ingestion run history |
| `POST` | `/api/indexes/{name}/check-consistency` | Admin | Trigger Arrow IPC ↔ FAISS ID alignment check. Writes result to `indexes` table |
| `GET` | `/api/indexes/{name}/artifacts` | Admin, Ops | Returns signed download URLs for `.arrow`, `.faiss`, `run_summary.json` |
| `DELETE` | `/api/indexes/{name}` | Admin | Soft-delete with 30s undo window. Requires `X-Confirm-Index-Name` header |
| `POST` | `/api/indexes/{name}/restore` | Admin | Undo soft-delete within undo window |

### Configurations

| Method | Endpoint | Role | Description |
|---|---|---|---|
| `GET` | `/api/configs` | All | List saved pipeline configurations |
| `POST` | `/api/configs` | Admin | Save a new named configuration |
| `PUT` | `/api/configs/{config_id}` | Admin | Update existing configuration |
| `DELETE` | `/api/configs/{config_id}` | Admin | Delete configuration |

### Auth & Audit

| Method | Endpoint | Role | Description |
|---|---|---|---|
| `POST` | `/api/auth/token` | — | Issue JWT. Body: `{ "username": "...", "password": "..." }` |
| `POST` | `/api/auth/refresh` | Any | Refresh JWT token |
| `GET` | `/api/audit` | Admin, Read-only | Paginated audit log. Query params: `user`, `action`, `date_from`, `date_to` |

### SSE Event Schema

Events sent on `/api/runs/{run_id}/stream`:

```json
// Stage update
{
  "event": "stage_update",
  "data": {
    "stage": "OP-3",
    "status": "running",
    "elapsed_ms": 1240,
    "rows_processed": 3840
  }
}

// Batch update
{
  "event": "batch_update",
  "data": {
    "batch_id": "batch-12",
    "status": "failed",
    "error_class": "EmbedModelError",
    "error_message": "Connection timeout after 30s",
    "rows_affected": 128
  }
}

// Run complete
{
  "event": "run_complete",
  "data": {
    "run_id": "run-0047",
    "status": "failed",
    "total_elapsed_s": 4.1,
    "rows_ingested": 2688,
    "rows_failed": 412,
    "speedup_x": null
  }
}

// Throughput tick (every 5s during active run)
{
  "event": "throughput_tick",
  "data": {
    "tickets_per_sec": 487,
    "timestamp": "2026-05-12T10:34:22Z"
  }
}
```

### Error Response Shape

All API errors return:

```json
{
  "error": {
    "code": "BATCH_RETRY_CONFLICT",
    "message": "Run run-0049 is still active. Retry is blocked until the run completes.",
    "run_id": "run-0049",
    "http_status": 409
  }
}
```

---

## 8. Data Model — SQLite Schema

SQLite is the permanent datastore for v0.1 and beyond at this deployment scale. WAL mode enabled. Single file: `kb_admin.db`.

### `runs`

```sql
CREATE TABLE runs (
    run_id          TEXT PRIMARY KEY,          -- "run-0049"
    source_filename TEXT NOT NULL,
    source_type     TEXT NOT NULL,             -- "zendesk" | "jira"
    config_id       TEXT,                      -- FK → configs.config_id (nullable if config deleted)
    index_name      TEXT NOT NULL,
    status          TEXT NOT NULL,             -- "queued" | "running" | "done" | "failed" | "partial"
    triggered_by    TEXT NOT NULL,             -- username
    trigger_type    TEXT NOT NULL,             -- "manual" | "scheduled" | "retry"
    rows_total      INTEGER,
    rows_ingested   INTEGER,
    rows_failed     INTEGER,
    batch_size      INTEGER NOT NULL,
    max_workers     INTEGER NOT NULL,
    embed_model     TEXT NOT NULL,
    max_chunk_chars INTEGER NOT NULL,
    null_policy     TEXT NOT NULL,
    append_mode     INTEGER NOT NULL DEFAULT 0, -- 0 = overwrite, 1 = append
    t_load_ms       INTEGER,
    t_preprocess_ms INTEGER,
    t_embed_ms      INTEGER,
    t_upsert_ms     INTEGER,
    t_total_ms      INTEGER,
    baseline_t_ms   INTEGER,                   -- Pandas baseline time for speedup calc
    speedup_x       REAL,
    success_rate    REAL,
    artifact_arrow  TEXT,                      -- filesystem path
    artifact_faiss  TEXT,
    artifact_summary TEXT,
    artifact_failed_rows TEXT,
    error_summary   TEXT,                      -- JSON array of top-level error messages
    queued_at       TEXT NOT NULL,             -- ISO8601
    started_at      TEXT,
    completed_at    TEXT
);

CREATE INDEX idx_runs_status       ON runs (status);
CREATE INDEX idx_runs_index_name   ON runs (index_name);
CREATE INDEX idx_runs_completed_at ON runs (completed_at DESC);
```

### `batches`

```sql
CREATE TABLE batches (
    batch_id        TEXT NOT NULL,             -- "batch-12"
    run_id          TEXT NOT NULL REFERENCES runs(run_id),
    batch_index     INTEGER NOT NULL,          -- 0-based position in run
    rows            INTEGER NOT NULL,
    status          TEXT NOT NULL,             -- "queued" | "running" | "done" | "failed"
    embed_duration_ms INTEGER,
    error_class     TEXT,
    error_message   TEXT,
    error_stack     TEXT,                      -- full stack trace, stored separately
    affected_row_ids TEXT,                     -- JSON array of row IDs (capped at 100; full set in failed_rows.json)
    started_at      TEXT,
    completed_at    TEXT,
    PRIMARY KEY (batch_id, run_id)
);

CREATE INDEX idx_batches_run_id ON batches (run_id);
CREATE INDEX idx_batches_status ON batches (run_id, status);
```

### `indexes`

```sql
CREATE TABLE indexes (
    index_name          TEXT PRIMARY KEY,
    doc_count           INTEGER NOT NULL DEFAULT 0,
    embed_dim           INTEGER NOT NULL,
    embed_model         TEXT NOT NULL,
    last_updated        TEXT NOT NULL,         -- ISO8601
    size_bytes_arrow    INTEGER,
    size_bytes_faiss    INTEGER,
    artifact_dir        TEXT NOT NULL,
    consistency_status  TEXT NOT NULL DEFAULT 'unchecked', -- "ok" | "mismatch" | "unchecked"
    consistency_checked_at TEXT,
    soft_deleted        INTEGER NOT NULL DEFAULT 0,
    soft_deleted_at     TEXT,
    soft_deleted_by     TEXT
);
```

### `run_events`

Append-only event log. Powers the SSE stream and the throughput sparkline.

```sql
CREATE TABLE run_events (
    event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id      TEXT NOT NULL REFERENCES runs(run_id),
    event_type  TEXT NOT NULL,                -- "stage_update" | "batch_update" | "run_complete" | "throughput_tick"
    payload     TEXT NOT NULL,               -- JSON
    recorded_at TEXT NOT NULL                -- ISO8601
);

CREATE INDEX idx_run_events_run_id     ON run_events (run_id);
CREATE INDEX idx_run_events_recorded_at ON run_events (recorded_at DESC);
```

Retention: events older than 30 days purged by a nightly `DELETE WHERE recorded_at < datetime('now', '-30 days')` triggered by the FastAPI startup scheduler.

### `configs`

```sql
CREATE TABLE configs (
    config_id       TEXT PRIMARY KEY,
    config_name     TEXT NOT NULL UNIQUE,
    source_type     TEXT,                      -- null = auto-detect
    batch_size      INTEGER NOT NULL DEFAULT 128,
    max_workers     INTEGER NOT NULL DEFAULT 4,
    max_chunk_chars INTEGER NOT NULL DEFAULT 512,
    min_chunk_chars INTEGER NOT NULL DEFAULT 20,
    null_policy     TEXT NOT NULL DEFAULT 'drop',
    faiss_factory   TEXT NOT NULL DEFAULT 'Flat',
    embed_model     TEXT NOT NULL DEFAULT 'all-MiniLM-L6-v2',
    created_by      TEXT NOT NULL,
    created_at      TEXT NOT NULL,
    updated_at      TEXT
);
```

### `users`

```sql
CREATE TABLE users (
    username        TEXT PRIMARY KEY,
    password_hash   TEXT NOT NULL,             -- bcrypt
    role            TEXT NOT NULL,             -- "admin" | "ops" | "readonly"
    created_at      TEXT NOT NULL,
    last_login      TEXT
);
```

### `audit_log`

```sql
CREATE TABLE audit_log (
    log_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    username    TEXT NOT NULL,
    action      TEXT NOT NULL,                 -- "run.trigger" | "run.retry" | "index.delete" | "config.update" | ...
    target_type TEXT,                          -- "run" | "index" | "config" | "schedule"
    target_id   TEXT,
    detail      TEXT,                          -- JSON: changed fields, config snapshot, etc.
    ip_address  TEXT,
    recorded_at TEXT NOT NULL
);

CREATE INDEX idx_audit_log_username    ON audit_log (username);
CREATE INDEX idx_audit_log_action      ON audit_log (action);
CREATE INDEX idx_audit_log_recorded_at ON audit_log (recorded_at DESC);
```

---

## 9. Real-time Layer

### Approach: FastAPI SSE via `StreamingResponse`

No separate real-time infrastructure. The FastAPI backend streams SSE events from the `run_events` table using a polling loop over an async generator. This is sufficient for the expected concurrent ops load (< 10 simultaneous watchers per deployment).

```python
# Conceptual shape — not production code
async def run_event_stream(run_id: str, db: Session):
    last_event_id = 0
    while True:
        events = db.query(RunEvent).filter(
            RunEvent.run_id == run_id,
            RunEvent.event_id > last_event_id
        ).order_by(RunEvent.event_id).all()

        for event in events:
            yield f"event: {event.event_type}\ndata: {event.payload}\n\n"
            last_event_id = event.event_id

        # Check if run is complete — if so, close stream
        run = db.query(Run).filter(Run.run_id == run_id).first()
        if run.status in ("done", "failed", "partial"):
            break

        await asyncio.sleep(1)  # 1s polling interval on the event log
```

### Client-side SSE handling

- Connect on run detail page load if `status = 'running'`.
- On `run_complete` event: update status badge, disable the retry button if status is `done`, stop the SSE connection.
- On connection drop: display "Reconnecting…" banner, retry SSE with exponential backoff (1s → 2s → 4s → 8s cap).
- Pause SSE polling when `document.visibilityState = 'hidden'` (Page Visibility API). Resume on tab focus.
- Fall back to 5-second REST poll (`GET /api/runs/{run_id}`) if SSE is blocked by a network proxy.

### Throughput Sparkline Source

The home screen sparkline reads `run_events WHERE event_type = 'throughput_tick' AND recorded_at > datetime('now', '-30 minutes')`, sorted ascending. The frontend re-queries on a 10-second interval. No SSE needed for the sparkline — REST poll is appropriate.

---

## 10. Component Inventory

| Component | Screen(s) | v | Behaviour Notes |
|---|---|---|---|
| **KPI Strip** | Home | 0.1 | 5 metrics. Large number, small label, trend delta. Updates via SSE on run events. |
| **Run Status Table** | Home, `/runs` | 0.1 | Sortable (default: newest first). Filterable by status, date, source. URL-persisted filters. CSV export. Compact / default density toggle. |
| **Pipeline Progress Bar** | Home (active run), Run Detail | 0.1 | 4 segments (OP-1 → OP-4). idle / active (shimmer) / done / failed states. Stage label + elapsed below. |
| **Batch Status Grid** | Run Detail | 0.1 | One cell per batch. Color = status. Click → scroll to Batch Detail Panel. Renders up to 256 batches in a single viewport without internal scroll. |
| **Stage Timeline Chart** | Run Detail | 0.1 | Horizontal proportional bar chart. Hover tooltip: exact ms + row count. Failed stages in red. |
| **Batch Detail Panel** | Run Detail | 0.1 | Appears below grid on cell click. Error class badge + human message + row IDs (10 inline, download for rest). Copy-JSON button. |
| **Speedup Gauge** | Home, Run Detail | 0.1 | Single number + 2.5× SLO target line. Green ≥ SLO, amber 1.8–2.5×, red < 1.8×. Historical sparkline behind it. |
| **Throughput Sparkline** | Home | 0.1 | 120×40px SVG line. 30-min window. Relative pattern only — no axis labels. |
| **Serialization Overhead Chart** | Run Detail | 0.1 | Side-by-side bar: Arrow total vs Pandas baseline estimate. Speedup multiplier label. |
| **Multi-step Wizard** | `/runs/new` | 0.1 | Full page, 5 steps. Step indicator at top. Validates before advancing. Step 5 shows diff from last run config. |
| **Pre-flight Validator** | Wizard Step 5 | 0.1 | Calls `/api/runs/validate`. Shows schema report inline — missing columns, null counts, detected source type. Must pass before "Start Ingestion" is enabled. |
| **Index Health Card** | `/indexes` | 0.1 | Doc count, dim, last-updated badge, consistency indicator, artifact download links. |
| **Confirmation Modal** | Index delete, Full re-run | 0.1 | Requires typed confirmation string (index name or "re-run"). Destructive button separated from cancel with 24px gap minimum. |
| **Error Detail Panel** | Run Detail | 0.1 | Error class badge + human message + next step text + link to spec anchor. Copy-JSON: full stack + run ID + timestamp as JSON. |
| **Skeleton Screens** | All data screens | 0.1 | Match actual layout shape. Shimmer animation. Shown after 300ms delay only. |
| **Cron Schedule Builder** | `/schedules` | 0.2 | Plain-language input → cron expression. Next-3-runs preview. |
| **Alert Rule Editor** | `/alerts` | 0.2 | Condition builder + channel selector. Test-fire before save. |

---

## 11. Role Access Matrix

| Feature | Admin | Ops | Read-only |
|---|---|---|---|
| View Run Dashboard | ✓ | ✓ | ✓ |
| View Run Detail & Logs | ✓ | ✓ | ✓ (no stack traces) |
| Download `run_summary.json` | ✓ | ✓ | ✗ |
| Download `failed_rows.json` | ✓ | ✓ | ✗ |
| Trigger New Ingestion | ✓ | ✗ | ✗ |
| Retry Failed Batches | ✓ | ✓ | ✗ |
| Full Re-run | ✓ | ✗ | ✗ |
| View Ingestion Config | ✓ | ✓ (read-only) | ✗ |
| Create / Edit Config | ✓ | ✗ | ✗ |
| View Index Registry | ✓ | ✓ | ✓ |
| Download Index Artifacts | ✓ | ✓ | ✗ |
| Trigger Consistency Check | ✓ | ✗ | ✗ |
| Retire / Archive Index | ✓ (+ confirm) | ✗ | ✗ |
| Create / Edit Schedules | ✓ | ✗ | ✗ |
| View Schedules | ✓ | ✓ | ✓ |
| Configure Alert Rules | ✓ | ✗ | ✗ |
| View Alert History | ✓ | ✓ | ✗ |
| View Audit Log | ✓ | Own actions | ✓ |
| Manage Users | ✓ | ✗ | ✗ |

**Enforcement:** Role claims are embedded in the JWT. Every API route decorator checks the claim. UI-level hiding is supplementary. A role check failure returns `403 { "error": { "code": "INSUFFICIENT_ROLE", ... } }`.

---

## 12. Performance Requirements

### API Response Times (p95, single-user load)

| Endpoint | Target p95 |
|---|---|
| `GET /api/runs` (page of 25) | < 120ms |
| `GET /api/runs/{id}` (with batch table) | < 200ms |
| `GET /api/indexes` | < 80ms |
| `POST /api/runs` (trigger, not ingest) | < 300ms |
| `POST /api/runs/{id}/retry` | < 300ms |
| `POST /api/runs/validate` (schema check) | < 2s for 50MB file |
| SSE first event latency | < 1s from run state change to browser receipt |

### SQLite Sizing

| Table | Expected rows @ 1 year | Size estimate |
|---|---|---|
| `runs` | ~3,650 (10/day) | < 5MB |
| `batches` | ~292,000 (80 batches × 3,650 runs) | < 50MB |
| `run_events` | ~1,000,000 (post-pruning: 30d rolling) | < 200MB |
| `audit_log` | ~20,000 | < 2MB |
| **Total** | | **< 260MB** |

WAL mode + `PRAGMA journal_mode=WAL` + `PRAGMA synchronous=NORMAL` is sufficient at this scale. No connection pooling needed for single-writer FastAPI process.

### SQLite Concurrency Note

SQLite WAL mode supports multiple concurrent readers with one writer. The FastAPI process is the sole writer. SSE stream readers are read-only. No connection pool library required — `check_same_thread=False` with a module-level connection and `threading.Lock` for writes is sufficient.

---

## 13. Error Handling

### API Error Codes

| Code | HTTP | Condition |
|---|---|---|
| `RUN_NOT_FOUND` | 404 | `run_id` does not exist |
| `INDEX_NOT_FOUND` | 404 | `index_name` does not exist |
| `RUN_STILL_ACTIVE` | 409 | Retry or delete attempted on an active run |
| `INDEX_SOFT_DELETED` | 410 | Operation attempted on a soft-deleted index |
| `UNDO_WINDOW_EXPIRED` | 409 | Restore attempted after 30s undo window |
| `INSUFFICIENT_ROLE` | 403 | Role claim does not meet route requirement |
| `SCHEMA_VALIDATION_FAILED` | 422 | Pre-flight found missing required columns |
| `INGEST_CONFIG_INVALID` | 422 | Config field out of allowed range |
| `DIM_MISMATCH_ON_APPEND` | 422 | Model dim ≠ existing index dim |
| `CONFIRM_HEADER_MISSING` | 400 | Destructive action missing `X-Confirm-Index-Name` header |

### Frontend Error Display Rules

- **API 4xx errors:** Display inline in the relevant form field or as a non-modal alert banner at the top of the current screen. Never navigate away.
- **API 5xx errors:** Display a full-screen error state with run ID, timestamp, and copy-JSON button. Link to `/runs` to continue working.
- **SSE disconnect:** Show a "Reconnecting…" amber banner. Do not show an error until 3 consecutive reconnect attempts fail. After 3 failures, show a "Live updates unavailable — switch to manual refresh" state with a 10-second auto-refresh button.
- **Empty states:** Every table with zero rows shows a context-appropriate empty state with a primary CTA (e.g., "No ingestion runs yet — Trigger your first run" on the home screen).

---

## 14. Testing Plan

### 14.1 Backend Unit Tests

| Test | Coverage |
|---|---|
| `test_run_status_transitions` | Valid transitions: queued → running → done/failed/partial |
| `test_retry_blocked_on_active_run` | `POST /retry` returns 409 when run status = 'running' |
| `test_retry_updates_batch_status` | Failed batch status → 'queued' after retry trigger |
| `test_soft_delete_index` | Index soft_deleted = 1, undo within window restores it |
| `test_undo_window_expired` | Restore after 30s returns 409 UNDO_WINDOW_EXPIRED |
| `test_dim_mismatch_on_append` | `POST /runs` with wrong model on existing index returns 422 |
| `test_role_enforcement_ops` | Ops role calling `POST /runs` returns 403 |
| `test_role_enforcement_readonly` | Read-only calling `POST /retry` returns 403 |
| `test_audit_log_on_delete` | Index soft-delete writes audit_log row |
| `test_sse_stream_emits_events` | SSE generator yields correct event types for a mock run |
| `test_run_events_pruning` | Events older than 30d removed by pruning function |
| `test_validate_missing_columns` | Pre-flight returns 422 with missing column names |
| `test_estimate_uses_historical_data` | `/estimate` uses mean throughput from last 5 completed runs |

### 14.2 Frontend Integration Tests (Playwright)

| Test | Scenario |
|---|---|
| `test_home_kpi_strip_updates` | Trigger a mock run via API; verify KPI strip values update without page reload |
| `test_run_detail_batch_grid` | Navigate to a failed run; verify failed batch cells render red; click → detail panel appears |
| `test_retry_button_disabled_on_active` | Load an active run detail page; verify retry button is disabled with correct tooltip |
| `test_wizard_step_advance_validation` | Leave required field empty; verify "Next" is disabled with inline error |
| `test_wizard_schema_preflight` | Upload a CSV with a missing required column; verify pre-flight error appears before "Start Ingestion" is enabled |
| `test_destructive_confirm_modal` | Click "Retire Index"; verify modal appears; submitting wrong name keeps modal open; correct name closes and removes index from list |
| `test_role_ops_hides_admin_nav` | Login as ops user; verify "New Ingestion" nav item is disabled (not hidden); clicking it shows role tooltip |
| `test_sse_reconnect_banner` | Simulate SSE disconnect; verify "Reconnecting…" banner appears; simulate reconnect; banner disappears |
| `test_url_filter_persistence` | Apply status=failed filter; refresh page; verify filter is still applied |
| `test_copy_json_error` | Click copy-JSON on failed batch; verify clipboard content is valid JSON with run_id and timestamp |

### 14.3 SQLite Schema Tests

| Test | Coverage |
|---|---|
| `test_migrations_idempotent` | Run migrations twice; no errors |
| `test_wal_mode_enabled` | `PRAGMA journal_mode` returns `wal` after init |
| `test_foreign_key_constraints` | Insert batch with non-existent run_id; verify FK error |
| `test_event_pruning_query` | Insert events at t-31d; verify pruning removes them and leaves t-29d events |

### 14.4 Test Fixtures

- `fixtures/runs_seed.sql` — 50 runs (mix of statuses, source types, index names). Generated by `make fixtures`.
- `fixtures/run_events_seed.sql` — 5,000 events across the 50 seeded runs.
- `fixtures/users_seed.sql` — one user per role (admin/ops/readonly), bcrypt-hashed test passwords.

---

## 15. Build Roadmap

### v0.1 — Run Visibility + Ops Recovery (Weeks 1–3, parallel to kb-ingestor v0.1)

**Week 1:**
- FastAPI app skeleton. SQLite init + all table migrations. JWT auth with 3 roles.
- `POST /api/runs` (wraps kb-ingestor `ingest()`) + `GET /api/runs` + `GET /api/runs/{id}`.
- Background task: write `run_events` as kb-ingestor emits stage/batch updates.
- Basic React frontend: home screen KPI strip + recent runs table (static, no SSE yet).

**Week 2:**
- SSE stream endpoint + frontend SSE client. Live pipeline progress bar.
- Run detail page: stage timeline, batch status grid, batch detail panel.
- Error detail panel with copy-JSON. Download endpoints for `run_summary.json` and `failed_rows.json`.
- `POST /api/runs/{id}/retry` + frontend retry button with disabled-state guard.

**Week 3:**
- Index health screen. Artifact download via signed URL. Consistency check trigger.
- Pre-flight schema validation (`POST /api/runs/validate`).
- New Ingestion Wizard (5 steps, full page). Saved configurations CRUD.
- Role enforcement hardening. Audit log writes. Skeleton screens on all data pages.

### v0.1.1 — Hardening (Week 4)

- URL-based filter state for runs table.
- SSE reconnect with exponential backoff + REST poll fallback.
- Speedup gauge with SLO target line and 30-day trend.
- CSV export for run history table.
- Page Visibility API pause for SSE.
- Run estimate endpoint using historical throughput data.

### v0.2 — Admin Control Plane (Sprint 2)

- Cron scheduler: create/edit/pause/delete schedules. Overlap guard.
- Alert rules builder + Slack/email channel config. Alert history log.
- Silence windows for alerts.
- Config diff on Wizard step 5 (changed fields vs last run).
- 30-day throughput trend chart. Per-model performance comparison.

---

## 16. Open Questions

| # | Question | Owner | Target |
|---|---|---|---|
| OQ-1 | Should the pre-flight dry-run in the Wizard upload the file to the server, or validate schema client-side first (via Arrow WASM)? Client-side would be faster but adds a dependency. | Engineering | Before Wizard build |
| OQ-2 | For the artifact signed URL: are we serving files directly from FastAPI (`FileResponse`) or from a local object store proxy? At 214MB Arrow files, direct FastAPI serving is fine for v0.1 but may need chunking. | Engineering | Before artifact download build |
| OQ-3 | SSE stream: should we emit throughput ticks from the ingestor process itself, or calculate them server-side by reading `run_events` at a 5s interval? Ingestor-emitted ticks are more accurate but require an IPC channel. | Engineering | Before SSE build |
| OQ-4 | User management UI: does v0.1 need a user management screen, or is it acceptable to manage users via a CLI script (`kb-admin-cli users add`) for the initial deployment? | AI Product | Before v0.1 cut |
| OQ-5 | Speedup baseline: the gauge compares against the Pandas baseline measured by `kb-ingest benchmark`. Should we re-measure the baseline on every run (adds ~20% overhead) or use the stored value from the last benchmark run? | Engineering | Before speedup gauge build |
| OQ-6 | Audit log retention: 1 year or indefinite? Audit logs are small (~2MB/year) but indefinite retention has compliance implications if ticket data is referenced in error messages. | AI Product + Legal | v0.1 cut |

---

## 17. Appendix: Dependency Stack

### Backend

| Package | Version | Role |
|---|---|---|
| `fastapi` | ≥ 0.111 | API framework + SSE via `StreamingResponse` |
| `uvicorn` | ≥ 0.29 | ASGI server |
| `python-jose` | ≥ 3.3 | JWT encode/decode |
| `passlib[bcrypt]` | ≥ 1.7 | Password hashing |
| `aiosqlite` | ≥ 0.20 | Async SQLite reads for SSE generator |
| `sqlite3` | stdlib | Sync SQLite writes (single writer, no pool needed) |
| `kb-ingestor` | v0.1.0 | Core ingest pipeline (local package) |
| `pydantic` | ≥ 2.0 | Request/response models |
| `python-multipart` | ≥ 0.0.9 | File upload handling in Wizard |
| `apscheduler` | ≥ 3.10 | Nightly `run_events` pruning job |

### Frontend

| Package | Version | Role |
|---|---|---|
| `react` | 18.x | UI framework |
| `vite` | 5.x | Build tool |
| `tailwindcss` | 3.x | Utility CSS |
| `tanstack/react-query` | 5.x | Server state, REST polling |
| `recharts` | 2.x | Stage timeline chart, speedup gauge, sparkline |
| `react-router-dom` | 6.x | Client-side routing |

### Dev / Test

| Package | Role |
|---|---|
| `pytest` + `pytest-asyncio` | Backend tests |
| `httpx` | FastAPI test client (async) |
| `playwright` | Frontend integration tests |
| `factory_boy` | SQLite fixture generation |

### Explicitly Excluded

- No Postgres — SQLite is permanent at this scale; migration path is not in scope.
- No Redis / Pub-Sub — FastAPI `StreamingResponse` + SQLite event polling is sufficient.
- No Celery / task queue — ingest runs are triggered synchronously as FastAPI background tasks.
- No separate auth service — JWT with bcrypt local user store is sufficient for single-team deployment.
- No Docker Compose in spec — deployment packaging is an ops concern outside this spec's scope.

---

*End of spec. Next: engineering kickoff → OQ-1 (pre-flight client vs server) + OQ-3 (SSE throughput source) → v0.1 sprint planning.*
