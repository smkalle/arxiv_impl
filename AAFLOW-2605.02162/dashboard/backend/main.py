"""
KB Ingestor Admin Dashboard — FastAPI backend entry point.
"""
from __future__ import annotations

import asyncio
import json
import random
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pathlib

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles

# Bootstrap sys.path so relative imports work when run via uvicorn
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from database import init_db, get_conn, _lock
from seed import seed_if_empty
from routes.auth import router as auth_router
from routes.runs import router as runs_router
from routes.indexes import router as indexes_router
from routes.configs import router as configs_router
from routes.audit import router as audit_router


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


async def _emit_synthetic_ticks() -> None:
    """Emit throughput_tick events every 5s for the seeded running run."""
    rng = random.Random()
    run_id = "run-0049"
    while True:
        await asyncio.sleep(5)

        conn = get_conn()
        row = conn.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
        conn.close()

        if row is None or row["status"] not in ("running", "queued"):
            break

        tps = rng.randint(380, 520)
        payload = json.dumps({"tickets_per_sec": tps, "timestamp": _iso(_now())})
        conn2 = get_conn()
        with _lock:
            conn2.execute(
                "INSERT INTO run_events (run_id, event_type, payload, recorded_at) VALUES (?,?,?,?)",
                (run_id, "throughput_tick", payload, _iso(_now())),
            )
            conn2.commit()
        conn2.close()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    init_db()
    seed_if_empty()

    # Start background tick emitter for the live demo run
    tick_task = asyncio.create_task(_emit_synthetic_ticks())

    yield

    # Shutdown
    tick_task.cancel()
    try:
        await tick_task
    except asyncio.CancelledError:
        pass


app = FastAPI(
    title="KB Ingestor Admin Dashboard",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow all origins in dev
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(auth_router)
app.include_router(runs_router)
app.include_router(indexes_router)
app.include_router(configs_router)
app.include_router(audit_router)


_FRONTEND = pathlib.Path(__file__).parent.parent / "frontend" / "index.html"


@app.get("/", response_class=HTMLResponse)
async def serve_frontend():
    """Serve the dashboard SPA."""
    if _FRONTEND.exists():
        return HTMLResponse(_FRONTEND.read_text(encoding="utf-8"))
    return HTMLResponse("<h2>Frontend not found. Expected: dashboard/frontend/index.html</h2>", status_code=404)


@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.1.0"}


# SSE throughput sparkline data endpoint (last 30 min)
@app.get("/api/sparkline")
async def sparkline():
    conn = get_conn()
    rows = conn.execute("""
        SELECT payload, recorded_at FROM run_events
        WHERE event_type='throughput_tick'
          AND recorded_at > datetime('now', '-30 minutes')
        ORDER BY recorded_at ASC
    """).fetchall()
    conn.close()
    points = []
    for r in rows:
        try:
            p = json.loads(r["payload"])
            points.append({"t": r["recorded_at"], "v": p.get("tickets_per_sec", 0)})
        except Exception:
            pass
    return {"points": points}
