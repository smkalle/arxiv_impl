# KB Ingestor — Admin & Ops Dashboard

> **v0.1.0** · Built on top of [`kb-ingestor`](../README.md) · Implements the spec at [`spec-kb-ingestor-admin-dashboard.md`](spec-kb-ingestor-admin-dashboard.md)

A purpose-built admin and ops console for the `kb-ingestor` pipeline. Gives ops teams full visibility into ingestion runs — from source file through Arrow pipeline stages to FAISS index health — without SSH access or manual log inspection.

**Design north star:** an ops engineer identifies a failed batch and triggers a targeted retry in under 90 seconds, from the browser.

---

## Quick start

```bash
# From the repo root — installs backend deps and starts uvicorn on port 8000
bash dashboard/start.sh
```

Then open **`http://localhost:8000`** in your browser.

> The frontend is a single HTML file served directly by the backend — no separate frontend server or build step needed.

### Test credentials

| Role | Username | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Ops / On-call | `ops` | `ops123` |
| Read-only | `readonly` | `read123` |

Change these before any non-local deployment — see [Security](#security).

---

## What's included (v0.1)

| Region | Route | Description |
|---|---|---|
| Run Dashboard | `/` | KPI strip, live pipeline progress bar, throughput sparkline, recent runs table |
| Run Detail | `/#/runs/{id}` | Stage timeline, batch status grid, error detail panel, retry actions |
| New Ingestion Wizard | `/#/runs/new` | 5-step wizard: source → config → model → output → preflight review |
| Index Health | `/#/indexes` | FAISS index registry, consistency check, artifact downloads |
| Audit Log | `/#/audit` | Paginated log of all write actions |

**Not included in v0.1** (spec §15): scheduler, alert rules, Slack/email notifications — targeted for v0.2.

---

## Architecture

```
dashboard/
  start.sh                  # installs deps, starts uvicorn
  frontend/
    index.html              # single-file SPA — vanilla JS + Tailwind CDN, no build step
  backend/
    main.py                 # FastAPI app + CORS + lifespan (DB init, seed, SSE tick emitter)
    database.py             # SQLite init, WAL mode, all 7 tables + indexes
    auth.py                 # JWT (HS256, 8h), bcrypt passwords, role enforcement deps
    schemas.py              # Pydantic v2 request/response models
    seed.py                 # demo data: 20 runs, 2 indexes, 3 users, 30min sparkline
    routes/
      auth.py               # POST /api/auth/token
      runs.py               # runs CRUD, SSE stream, retry, validate, estimate
      indexes.py            # registry, consistency check, soft-delete + undo
      configs.py            # saved config CRUD
      audit.py              # paginated audit log
  tests/
    test_dashboard_validation.py   # 73 API contract + frontend structure tests
    test_dashboard_ui.py           # 29 headless Chromium browser tests (Playwright)
  spec-kb-ingestor-admin-dashboard.md   # full technical product spec (17 sections)
  kb-ingestor-admin-dashboard-plan.html # interactive spec planning document
```

### Backend stack

| Package | Version | Role |
|---|---|---|
| `fastapi` | ≥ 0.111 | API framework + SSE via `StreamingResponse` |
| `uvicorn` | ≥ 0.29 | ASGI server |
| `python-jose[cryptography]` | ≥ 3.3 | JWT encode/decode |
| `bcrypt` | ≥ 4.0 | Password hashing |
| `aiosqlite` | ≥ 0.20 | Async SQLite reads for SSE generator |
| `python-multipart` | ≥ 0.0.9 | File upload in wizard |
| `apscheduler` | ≥ 3.10 | Nightly `run_events` pruning job |
| `pydantic` | ≥ 2.0 | Request/response validation |

### Frontend stack

Zero dependencies installed — everything loads from CDN at runtime:

- **Tailwind CSS** (CDN) — utility styling
- **Vanilla JS** — routing, fetch API, SSE client, SVG charts
- No React, no Vue, no build step

---

## API reference

Interactive docs at **`http://localhost:8000/docs`** (FastAPI auto-generated Swagger UI).

### Key endpoints

```
POST /api/auth/token                       issue JWT
GET  /api/runs                             paginated run history (filterable)
POST /api/runs                             trigger new ingestion run (Admin)
GET  /api/runs/{id}                        run detail with batches
GET  /api/runs/{id}/stream                 SSE live stage + batch events
POST /api/runs/{id}/retry                  retry failed batches (Admin + Ops)
POST /api/runs/validate                    pre-flight schema check (Admin)
GET  /api/indexes                          index registry
GET  /api/indexes/{name}                   index detail + run history
POST /api/indexes/{name}/check-consistency trigger Arrow ↔ FAISS alignment check (Admin)
DELETE /api/indexes/{name}                 soft-delete with 30s undo (Admin)
GET  /api/configs                          saved pipeline configurations
POST /api/configs                          create config (Admin)
GET  /api/audit                            audit log (Admin + Read-only)
GET  /api/sparkline                        throughput tick data for home sparkline
```

### SSE event types

Events on `GET /api/runs/{id}/stream`:

| Event | When |
|---|---|
| `stage_update` | OP-1/2/3/4 status or elapsed changes |
| `batch_update` | A batch completes, fails, or starts |
| `run_complete` | Run reaches terminal status |
| `throughput_tick` | Every 5s during active run |

---

## Role access matrix

| Feature | Admin | Ops | Read-only |
|---|---|---|---|
| View dashboard & run history | ✓ | ✓ | ✓ |
| View run detail | ✓ | ✓ | ✓ (no stack traces) |
| Download artifacts | ✓ | ✓ | ✗ |
| Trigger new ingestion | ✓ | ✗ | ✗ |
| Retry failed batches | ✓ | ✓ | ✗ |
| Create / edit configs | ✓ | ✗ | ✗ |
| Trigger consistency check | ✓ | ✗ | ✗ |
| Soft-delete index | ✓ | ✗ | ✗ |
| View audit log | ✓ | own actions | ✓ |

Role claims are embedded in the JWT and enforced at the API layer on every write route — UI hiding is supplementary only.

---

## Running the tests

Backend must be running on port 8000 before running browser tests.

```bash
# API contract tests + frontend structure validation (no browser needed)
pytest dashboard/tests/test_dashboard_validation.py -v

# Headless Chromium browser tests (requires Playwright + Chromium)
playwright install chromium
pytest dashboard/tests/test_dashboard_ui.py -v

# Full suite
pytest dashboard/tests/ -v
```

**Test results:** 102/102 passing (73 API/structural + 29 browser).

---

## Database

SQLite (`dashboard/backend/kb_admin.db`) with WAL mode. Created automatically on first startup.

Tables: `runs`, `batches`, `indexes`, `run_events`, `configs`, `users`, `audit_log`.

The `run_events` table is pruned nightly — events older than 30 days are deleted by an APScheduler job registered at startup.

To reset to a clean seeded state, delete `kb_admin.db` and restart.

---

## Security

**This is a development/internal-ops tool. Before any non-local deployment:**

1. Change `KB_ADMIN_SECRET` env var (used for JWT signing — defaults to a hardcoded dev value).
2. Replace the seeded test passwords (`admin123`, `ops123`, `read123`) via the users table.
3. Restrict CORS origins in `main.py` (currently `allow_origins=["*"]`).
4. Run behind a reverse proxy (nginx/caddy) with TLS.
5. Consider network-level access control — this dashboard exposes pipeline configuration.

---

## Contributing

See [`CONTRIBUTING.md`](../CONTRIBUTING.md) at the repo root.

Open questions before v0.1 cut are tracked in [`spec-kb-ingestor-admin-dashboard.md`](spec-kb-ingestor-admin-dashboard.md) §16.
