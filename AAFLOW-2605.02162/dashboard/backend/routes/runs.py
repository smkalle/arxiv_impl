"""Run management routes."""
from __future__ import annotations

import asyncio
import json
import random
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import require_admin, require_any, require_ops_or_admin, _get_current_user
from database import get_conn, _lock
from schemas import (
    BatchOut,
    EstimateRequest,
    EstimateResponse,
    RetryRequest,
    RunOut,
    RunsPage,
    TriggerRunRequest,
    ValidateRequest,
    ValidateResponse,
)

router = APIRouter(prefix="/api/runs", tags=["runs"])


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_run(row, batches=None) -> RunOut:
    d = dict(row)
    if d.get("error_summary") and isinstance(d["error_summary"], str):
        try:
            d["error_summary"] = json.loads(d["error_summary"])
        except Exception:
            pass
    run = RunOut(**{k: v for k, v in d.items() if k in RunOut.model_fields})
    if batches is not None:
        run.batches = [_row_to_batch(b) for b in batches]
    return run


def _row_to_batch(row) -> BatchOut:
    d = dict(row)
    if d.get("affected_row_ids") and isinstance(d["affected_row_ids"], str):
        try:
            d["affected_row_ids"] = json.loads(d["affected_row_ids"])
        except Exception:
            pass
    return BatchOut(**{k: v for k, v in d.items() if k in BatchOut.model_fields})


def _write_audit(username: str, action: str, target_type: str, target_id: str, detail: dict, ip: str = None):
    conn = get_conn()
    with _lock:
        conn.execute("""
            INSERT INTO audit_log (username, action, target_type, target_id, detail, ip_address, recorded_at)
            VALUES (?,?,?,?,?,?,?)
        """, (username, action, target_type, target_id, json.dumps(detail), ip, _iso(_now())))
        conn.commit()
    conn.close()


# ── GET /api/runs ────────────────────────────────────────────────────────────

@router.get("", response_model=RunsPage)
async def list_runs(
    status: Optional[str] = Query(None),
    source_type: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(25, ge=1, le=100),
    user=Depends(require_any),
):
    conn = get_conn()
    filters = ["1=1"]
    params = []

    if status:
        filters.append("status=?")
        params.append(status)
    if source_type:
        filters.append("source_type=?")
        params.append(source_type)
    if date_from:
        filters.append("queued_at >= ?")
        params.append(date_from)
    if date_to:
        filters.append("queued_at <= ?")
        params.append(date_to)

    where = " AND ".join(filters)
    total = conn.execute(f"SELECT COUNT(*) FROM runs WHERE {where}", params).fetchone()[0]
    offset = (page - 1) * limit
    rows = conn.execute(
        f"SELECT * FROM runs WHERE {where} ORDER BY queued_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return RunsPage(
        items=[_row_to_run(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
    )


# ── POST /api/runs ───────────────────────────────────────────────────────────

@router.post("", response_model=RunOut, status_code=201)
async def trigger_run(
    body: TriggerRunRequest,
    background_tasks: BackgroundTasks,
    request: Request,
    user=Depends(require_admin),
):
    run_id = f"run-{uuid.uuid4().hex[:6]}"
    now = _now()

    conn = get_conn()
    with _lock:
        conn.execute("""
            INSERT INTO runs
              (run_id, source_filename, source_type, config_id, index_name, status,
               triggered_by, trigger_type, rows_total, rows_ingested, rows_failed,
               batch_size, max_workers, embed_model, max_chunk_chars, null_policy,
               append_mode, queued_at, started_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            run_id, body.source_filename, body.source_type, body.config_id,
            body.index_name, "queued", user["sub"], "manual",
            None, 0, 0,
            body.batch_size, body.max_workers, body.embed_model,
            body.max_chunk_chars, body.null_policy, int(body.append_mode),
            _iso(now), _iso(now),
        ))
        conn.commit()

    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    conn.close()

    # Write audit log
    _write_audit(user["sub"], "run.trigger", "run", run_id,
                 {"source": body.source_filename, "index": body.index_name},
                 str(request.client.host) if request.client else None)

    # Start simulated background ingest
    background_tasks.add_task(_simulate_ingest, run_id, body.source_filename)

    return _row_to_run(row)


async def _simulate_ingest(run_id: str, source_filename: str) -> None:
    """Simulate a kb_ingestor run by writing events over ~10 seconds."""
    await asyncio.sleep(0.5)

    rng = random.Random()
    rows_total = rng.randint(3000, 8000)
    batch_size = 128
    num_batches = rows_total // batch_size

    now = _now()

    def write(sql, params):
        conn = get_conn()
        with _lock:
            conn.execute(sql, params)
            conn.commit()
        conn.close()

    # Mark as running
    write("UPDATE runs SET status='running', rows_total=?, started_at=? WHERE run_id=?",
          (rows_total, _iso(_now()), run_id))

    stages = [
        ("OP-1", "load",       1.5),
        ("OP-2", "preprocess", 0.8),
        ("OP-3", "embed",      5.0),
        ("OP-4", "upsert",     1.0),
    ]
    timings = {}

    for stage_id, stage_key, duration in stages:
        # Emit stage_update: running
        payload = json.dumps({"stage": stage_id, "status": "running",
                              "elapsed_ms": 0, "rows_processed": 0})
        write("INSERT INTO run_events (run_id, event_type, payload, recorded_at) VALUES (?,?,?,?)",
              (run_id, "stage_update", payload, _iso(_now())))

        # Simulate throughput ticks during embed
        if stage_key == "embed":
            for tick in range(int(duration)):
                await asyncio.sleep(1)
                tps = rng.randint(380, 520)
                tp = json.dumps({"tickets_per_sec": tps, "timestamp": _iso(_now())})
                write("INSERT INTO run_events (run_id, event_type, payload, recorded_at) VALUES (?,?,?,?)",
                      (run_id, "throughput_tick", tp, _iso(_now())))
        else:
            await asyncio.sleep(duration)

        timings[stage_key] = int(duration * 1000)

        payload = json.dumps({"stage": stage_id, "status": "done",
                              "elapsed_ms": timings[stage_key],
                              "rows_processed": rows_total})
        write("INSERT INTO run_events (run_id, event_type, payload, recorded_at) VALUES (?,?,?,?)",
              (run_id, "stage_update", payload, _iso(_now())))

    # Seed batches
    conn2 = get_conn()
    with _lock:
        for i in range(num_batches):
            rows = batch_size if i < num_batches - 1 else rows_total - batch_size * (num_batches - 1)
            conn2.execute("""
                INSERT OR IGNORE INTO batches
                  (batch_id, run_id, batch_index, rows, status, embed_duration_ms,
                   started_at, completed_at)
                VALUES (?,?,?,?,?,?,?,?)
            """, (f"batch-{i:02d}", run_id, i, rows, "done",
                  rng.randint(200, 2000), _iso(now), _iso(_now())))
        conn2.commit()
    conn2.close()

    speedup = round(rng.uniform(2.5, 3.1), 2)
    t_total = sum(timings.values())
    baseline = int(t_total * speedup)

    write("""
        UPDATE runs SET status='done', rows_ingested=?, rows_failed=0,
          t_load_ms=?, t_preprocess_ms=?, t_embed_ms=?, t_upsert_ms=?,
          t_total_ms=?, baseline_t_ms=?, speedup_x=?, success_rate=1.0,
          completed_at=?
        WHERE run_id=?
    """, (rows_total, timings["load"], timings["preprocess"], timings["embed"],
          timings["upsert"], t_total, baseline, speedup, _iso(_now()), run_id))

    complete_payload = json.dumps({
        "run_id": run_id, "status": "done",
        "total_elapsed_s": t_total / 1000,
        "rows_ingested": rows_total, "rows_failed": 0,
        "speedup_x": speedup,
    })
    write("INSERT INTO run_events (run_id, event_type, payload, recorded_at) VALUES (?,?,?,?)",
          (run_id, "run_complete", complete_payload, _iso(_now())))


# ── GET /api/runs/{run_id} ───────────────────────────────────────────────────

@router.get("/{run_id}", response_model=RunOut)
async def get_run(run_id: str, user=Depends(require_any)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "RUN_NOT_FOUND", "message": f"Run {run_id} not found"})
    batches = conn.execute(
        "SELECT * FROM batches WHERE run_id=? ORDER BY batch_index", (run_id,)
    ).fetchall()
    conn.close()
    return _row_to_run(row, batches)


# ── GET /api/runs/{run_id}/stream ────────────────────────────────────────────

@router.get("/{run_id}/stream")
async def stream_run(run_id: str, user=Depends(require_any)):
    conn = get_conn()
    row = conn.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, {"code": "RUN_NOT_FOUND", "message": f"Run {run_id} not found"})

    async def event_generator():
        last_event_id = 0
        max_polls = 120  # 120 seconds max

        for _ in range(max_polls):
            conn2 = get_conn()
            events = conn2.execute(
                "SELECT * FROM run_events WHERE run_id=? AND event_id>? ORDER BY event_id",
                (run_id, last_event_id),
            ).fetchall()

            for ev in events:
                last_event_id = ev["event_id"]
                yield f"event: {ev['event_type']}\ndata: {ev['payload']}\n\n"

            run_row = conn2.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
            conn2.close()

            if run_row and run_row["status"] in ("done", "failed", "partial"):
                yield "event: close\ndata: {}\n\n"
                break

            await asyncio.sleep(1)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ── POST /api/runs/{run_id}/retry ────────────────────────────────────────────

@router.post("/{run_id}/retry")
async def retry_batches(
    run_id: str,
    body: RetryRequest,
    request: Request,
    user=Depends(require_ops_or_admin),
):
    conn = get_conn()
    row = conn.execute("SELECT status FROM runs WHERE run_id=?", (run_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "RUN_NOT_FOUND", "message": f"Run {run_id} not found"})
    if row["status"] == "running":
        conn.close()
        raise HTTPException(409, {"code": "RUN_STILL_ACTIVE",
                                  "message": f"Run {run_id} is still active. Retry blocked."})

    with _lock:
        for bid in body.batch_ids:
            conn.execute(
                "UPDATE batches SET status='queued', error_class=NULL, error_message=NULL WHERE batch_id=? AND run_id=?",
                (bid, run_id),
            )
        conn.execute("UPDATE runs SET status='running' WHERE run_id=?", (run_id,))
        conn.commit()
    conn.close()

    _write_audit(user["sub"], "run.retry", "run", run_id,
                 {"batch_ids": body.batch_ids},
                 str(request.client.host) if request.client else None)

    return {"status": "ok", "run_id": run_id, "retried_batches": len(body.batch_ids)}


# ── POST /api/runs/validate ──────────────────────────────────────────────────

@router.post("/validate", response_model=ValidateResponse)
async def validate_source(body: ValidateRequest, user=Depends(require_admin)):
    """Simulate pre-flight schema validation."""
    fname = body.source_filename.lower()
    detected = "zendesk" if fname.endswith(".csv") else "jira"

    zendesk_cols = ["id", "subject", "description", "status", "created_at", "assignee", "tags"]
    jira_cols    = ["id", "summary", "description", "status", "created", "assignee", "labels"]
    expected = zendesk_cols if detected == "zendesk" else jira_cols

    # Simulate: all columns present
    missing: list[str] = []
    null_counts = {c: 0 for c in expected}

    return ValidateResponse(
        valid=len(missing) == 0,
        detected_source_type=detected,
        row_count=5000,
        columns_found=expected,
        columns_missing=missing,
        null_counts=null_counts,
        message="Schema valid. Ready to ingest." if not missing else f"Missing columns: {missing}",
    )


# ── POST /api/runs/estimate ──────────────────────────────────────────────────

@router.post("/estimate", response_model=EstimateResponse)
async def estimate_run(body: EstimateRequest, user=Depends(require_admin)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT t_total_ms, rows_total FROM runs WHERE status='done' AND t_total_ms IS NOT NULL ORDER BY completed_at DESC LIMIT 5"
    ).fetchall()
    conn.close()

    if rows:
        throughputs = [r["rows_total"] / (r["t_total_ms"] / 1000) for r in rows if r["rows_total"]]
        p50 = sorted(throughputs)[len(throughputs) // 2]
    else:
        p50 = 450.0

    est_s = body.row_count / p50
    return EstimateResponse(
        estimated_seconds=round(est_s, 1),
        p50_throughput=round(p50, 1),
        estimated_batches=body.row_count // body.batch_size,
    )


# ── GET /api/runs/{run_id}/artifacts/* ──────────────────────────────────────

@router.get("/{run_id}/artifacts/summary")
async def download_summary(run_id: str, user=Depends(require_ops_or_admin)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, {"code": "RUN_NOT_FOUND", "message": f"Run {run_id} not found"})

    summary = {
        "run_id": row["run_id"],
        "status": row["status"],
        "rows_total": row["rows_total"],
        "rows_ingested": row["rows_ingested"],
        "speedup_x": row["speedup_x"],
        "embed_dim": 384,
        "t_total_ms": row["t_total_ms"],
    }
    from fastapi.responses import JSONResponse
    return JSONResponse(content=summary, headers={
        "Content-Disposition": f'attachment; filename="run_summary_{run_id}.json"'
    })


@router.get("/{run_id}/artifacts/failed-rows")
async def download_failed_rows(run_id: str, user=Depends(require_ops_or_admin)):
    conn = get_conn()
    batches = conn.execute(
        "SELECT batch_id, affected_row_ids FROM batches WHERE run_id=? AND status='failed'",
        (run_id,),
    ).fetchall()
    conn.close()

    failed = []
    for b in batches:
        if b["affected_row_ids"]:
            try:
                failed.extend(json.loads(b["affected_row_ids"]))
            except Exception:
                pass

    from fastapi.responses import JSONResponse
    return JSONResponse(content={"run_id": run_id, "failed_row_ids": failed}, headers={
        "Content-Disposition": f'attachment; filename="failed_rows_{run_id}.json"'
    })
