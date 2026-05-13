"""
Seed data generator for kb-ingestor admin dashboard.
Generates realistic-looking run history for immediate UI demo.
"""
from __future__ import annotations

import json
import random
import uuid
from datetime import datetime, timedelta, timezone

from auth import hash_password
from database import get_conn


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def seed_if_empty() -> None:
    conn = get_conn()
    cur = conn.cursor()

    # Check if already seeded
    cur.execute("SELECT COUNT(*) FROM users")
    if cur.fetchone()[0] > 0:
        conn.close()
        return

    print("[seed] Seeding database with demo data…")
    _seed_users(cur)
    _seed_indexes(cur)
    _seed_configs(cur)
    _seed_runs(cur)
    conn.commit()
    conn.close()
    print("[seed] Done.")


def _seed_users(cur) -> None:
    users = [
        ("admin",    hash_password("admin123"),   "admin",    "2026-04-01T00:00:00Z"),
        ("ops",      hash_password("ops123"),     "ops",      "2026-04-01T00:00:00Z"),
        ("readonly", hash_password("read123"),    "readonly", "2026-04-01T00:00:00Z"),
    ]
    cur.executemany(
        "INSERT OR IGNORE INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
        users,
    )


def _seed_indexes(cur) -> None:
    now = _now()
    indexes = [
        {
            "index_name": "support-kb",
            "doc_count": 48312,
            "embed_dim": 384,
            "embed_model": "all-MiniLM-L6-v2",
            "last_updated": _iso(now - timedelta(hours=2)),
            "size_bytes_arrow": 214 * 1024 * 1024,
            "size_bytes_faiss": 74 * 1024 * 1024,
            "artifact_dir": "/data/artifacts/support-kb",
            "consistency_status": "ok",
            "consistency_checked_at": _iso(now - timedelta(hours=2)),
            "soft_deleted": 0,
        },
        {
            "index_name": "billing-kb",
            "doc_count": 12840,
            "embed_dim": 384,
            "embed_model": "all-MiniLM-L6-v2",
            "last_updated": _iso(now - timedelta(days=1)),
            "size_bytes_arrow": 58 * 1024 * 1024,
            "size_bytes_faiss": 19 * 1024 * 1024,
            "artifact_dir": "/data/artifacts/billing-kb",
            "consistency_status": "unchecked",
            "consistency_checked_at": None,
            "soft_deleted": 0,
        },
    ]
    for idx in indexes:
        cur.execute("""
            INSERT OR IGNORE INTO indexes
              (index_name, doc_count, embed_dim, embed_model, last_updated,
               size_bytes_arrow, size_bytes_faiss, artifact_dir,
               consistency_status, consistency_checked_at, soft_deleted)
            VALUES (:index_name,:doc_count,:embed_dim,:embed_model,:last_updated,
                    :size_bytes_arrow,:size_bytes_faiss,:artifact_dir,
                    :consistency_status,:consistency_checked_at,:soft_deleted)
        """, idx)


def _seed_configs(cur) -> None:
    now = _now()
    configs = [
        ("cfg-default", "Default Config",         None,       128, 4, 512, 20, "drop",  "Flat", "all-MiniLM-L6-v2"),
        ("cfg-fast",    "Fast Batch (Large)",      "zendesk",  256, 8, 256, 20, "drop",  "Flat", "all-MiniLM-L6-v2"),
        ("cfg-careful", "Careful (Raise on Null)", "jira",     64,  2, 512, 20, "raise", "Flat", "all-MiniLM-L6-v2"),
    ]
    for c in configs:
        cur.execute("""
            INSERT OR IGNORE INTO configs
              (config_id, config_name, source_type, batch_size, max_workers,
               max_chunk_chars, min_chunk_chars, null_policy, faiss_factory,
               embed_model, created_by, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (*c, "admin", _iso(now - timedelta(days=30))))


def _seed_runs(cur) -> None:
    """Generate 20 seeded runs with realistic data."""
    now = _now()
    sources_zendesk = [f"zendesk_export_2026-{m:02d}-{d:02d}.csv"
                       for m, d in [(4,1),(4,5),(4,8),(4,12),(4,15),(4,18),(4,22),(4,25),(4,28),(5,2),(5,5),(5,8),(5,10),(5,11)]]
    sources_jira    = [f"jira_export_2026-{m:02d}-{d:02d}.json"
                       for m, d in [(4,3),(4,10),(4,17),(4,24),(5,1),(5,7)]]

    # 15 done, 3 failed, 1 partial, 1 running (run-0049 is the running one)
    run_specs = []
    rng = random.Random(42)

    def make_run(
        run_num: int,
        status: str,
        source_file: str,
        index_name: str,
        hours_ago: float,
        rows_total: int,
        speedup: float | None,
        triggered_by: str = "admin",
    ):
        st = status
        qt = _iso(now - timedelta(hours=hours_ago + 0.02))
        sa = _iso(now - timedelta(hours=hours_ago))
        if status in ("done", "failed", "partial"):
            elapsed_s = rng.uniform(5, 15)
            ca = _iso(now - timedelta(hours=hours_ago) + timedelta(seconds=elapsed_s))
        else:
            ca = None
            elapsed_s = (now - (now - timedelta(hours=hours_ago))).total_seconds()

        rows_ingested = rows_total if status == "done" else (
            int(rows_total * rng.uniform(0.5, 0.9)) if status in ("partial", "running") else
            int(rows_total * rng.uniform(0.6, 0.85)) if status == "failed" else rows_total
        )
        rows_failed = rows_total - rows_ingested if status != "done" else 0

        t_load = rng.randint(300, 800)
        t_pre  = rng.randint(150, 400)
        t_emb  = rng.randint(2000, 8000)
        t_ups  = rng.randint(200, 600)
        t_tot  = t_load + t_pre + t_emb + t_ups
        baseline = int(t_tot * (speedup or 2.5)) if speedup else None

        src_type = "zendesk" if source_file.endswith(".csv") else "jira"

        run = {
            "run_id": f"run-{run_num:04d}",
            "source_filename": source_file,
            "source_type": src_type,
            "config_id": "cfg-default",
            "index_name": index_name,
            "status": st,
            "triggered_by": triggered_by,
            "trigger_type": "manual",
            "rows_total": rows_total,
            "rows_ingested": rows_ingested,
            "rows_failed": rows_failed,
            "batch_size": 128,
            "max_workers": 4,
            "embed_model": "all-MiniLM-L6-v2",
            "max_chunk_chars": 512,
            "null_policy": "drop",
            "append_mode": 1,
            "t_load_ms": t_load if status != "running" else None,
            "t_preprocess_ms": t_pre if status != "running" else None,
            "t_embed_ms": t_emb if status != "running" else None,
            "t_upsert_ms": t_ups if status != "running" else None,
            "t_total_ms": t_tot if status != "running" else None,
            "baseline_t_ms": baseline,
            "speedup_x": speedup,
            "success_rate": rows_ingested / rows_total if rows_total else None,
            "artifact_arrow": f"/data/artifacts/{index_name}/tickets.arrow",
            "artifact_faiss": f"/data/artifacts/{index_name}/index.faiss",
            "artifact_summary": f"/data/artifacts/{index_name}/run_summary.json",
            "artifact_failed_rows": f"/data/artifacts/{index_name}/failed_rows.json" if rows_failed else None,
            "error_summary": json.dumps(["EmbedModelError: timeout on batch-12"]) if status == "failed" else None,
            "queued_at": qt,
            "started_at": sa,
            "completed_at": ca,
        }
        run_specs.append(run)

    # Build 20 runs newest→oldest
    counter = 49  # start at run-0049 (running)

    # run-0049: currently running
    make_run(counter, "running", sources_zendesk[13], "support-kb", 0.1, 6400, None)
    counter -= 1

    # run-0048 to run-0035: mix of done
    done_sources = sources_zendesk[:12] + sources_jira[:2]
    for i, src in enumerate(done_sources[:14]):
        hours = 2 + i * 18
        sp = round(rng.uniform(2.5, 3.1), 2)
        idx = "support-kb" if i % 3 != 2 else "billing-kb"
        make_run(counter, "done", src, idx, hours, rng.randint(5000, 12000), sp)
        counter -= 1

    # run-0034: partial
    make_run(counter, "partial", sources_jira[2], "billing-kb", 2 + 14 * 18, 8000, None)
    counter -= 1

    # 3 failed runs interspersed
    for i, src in enumerate(sources_jira[3:]):
        hours = 2 + (15 + i * 7) * 18
        make_run(counter, "failed", src, "support-kb", hours, rng.randint(2000, 5000), None, triggered_by="ops")
        counter -= 1

    # Insert runs
    for r in run_specs:
        cur.execute("""
            INSERT OR IGNORE INTO runs
              (run_id, source_filename, source_type, config_id, index_name, status,
               triggered_by, trigger_type, rows_total, rows_ingested, rows_failed,
               batch_size, max_workers, embed_model, max_chunk_chars, null_policy,
               append_mode, t_load_ms, t_preprocess_ms, t_embed_ms, t_upsert_ms,
               t_total_ms, baseline_t_ms, speedup_x, success_rate,
               artifact_arrow, artifact_faiss, artifact_summary, artifact_failed_rows,
               error_summary, queued_at, started_at, completed_at)
            VALUES
              (:run_id,:source_filename,:source_type,:config_id,:index_name,:status,
               :triggered_by,:trigger_type,:rows_total,:rows_ingested,:rows_failed,
               :batch_size,:max_workers,:embed_model,:max_chunk_chars,:null_policy,
               :append_mode,:t_load_ms,:t_preprocess_ms,:t_embed_ms,:t_upsert_ms,
               :t_total_ms,:baseline_t_ms,:speedup_x,:success_rate,
               :artifact_arrow,:artifact_faiss,:artifact_summary,:artifact_failed_rows,
               :error_summary,:queued_at,:started_at,:completed_at)
        """, r)

    # Seed batches for each run
    for r in run_specs:
        _seed_batches(cur, r, rng)

    # Seed throughput tick events (last 30 min) for sparkline
    _seed_throughput_ticks(cur, rng, now)


def _seed_batches(cur, run: dict, rng: random.Random) -> None:
    rows_total = run["rows_total"] or 1000
    batch_size = run["batch_size"]
    num_batches = max(1, rows_total // batch_size)
    status = run["status"]
    failed_batch_index = rng.randint(num_batches // 2, num_batches - 1) if status == "failed" else None

    for i in range(num_batches):
        rows = batch_size if i < num_batches - 1 else (rows_total - batch_size * (num_batches - 1))
        if status == "done":
            b_status = "done"
            err_class = err_msg = None
        elif status == "failed" and i == failed_batch_index:
            b_status = "failed"
            err_class = rng.choice(["EmbedModelError", "BatchProcessingError", "EmbedDimMismatchError"])
            err_msg = {
                "EmbedModelError": "Connection timeout after 30s — model server unresponsive",
                "BatchProcessingError": "Unexpected null in required field 'subject' at row 42",
                "EmbedDimMismatchError": "Expected dim 384, got 768 — model mismatch",
            }[err_class]
        elif status == "failed" and i > (failed_batch_index or num_batches):
            b_status = "queued"
            err_class = err_msg = None
        elif status == "partial" and i >= num_batches - 3:
            b_status = rng.choice(["failed", "queued"])
            err_class = "BatchProcessingError" if b_status == "failed" else None
            err_msg = "Unexpected EOF in source file" if b_status == "failed" else None
        elif status == "running" and i >= num_batches * 2 // 3:
            b_status = "queued"
            err_class = err_msg = None
        elif status == "running" and i == num_batches * 2 // 3 - 1:
            b_status = "running"
            err_class = err_msg = None
        else:
            b_status = "done"
            err_class = err_msg = None

        started = run["started_at"]
        completed = run["completed_at"] if b_status in ("done", "failed") else None
        affected = json.dumps([f"row-{rng.randint(1000,9999)}" for _ in range(min(5, rows))]) if err_class else None

        cur.execute("""
            INSERT OR IGNORE INTO batches
              (batch_id, run_id, batch_index, rows, status,
               embed_duration_ms, error_class, error_message, affected_row_ids,
               started_at, completed_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """, (
            f"batch-{i:02d}", run["run_id"], i, rows, b_status,
            rng.randint(200, 2000) if b_status == "done" else None,
            err_class, err_msg, affected,
            started, completed,
        ))


def _seed_throughput_ticks(cur, rng: random.Random, now: datetime) -> None:
    """Seed throughput_tick events for the last 30 minutes across recent runs."""
    active_run_id = "run-0049"
    for minutes_ago in range(30, 0, -1):
        ts = _iso(now - timedelta(minutes=minutes_ago))
        tps = rng.randint(380, 520)
        payload = json.dumps({"tickets_per_sec": tps, "timestamp": ts})
        cur.execute("""
            INSERT INTO run_events (run_id, event_type, payload, recorded_at)
            VALUES (?,?,?,?)
        """, (active_run_id, "throughput_tick", payload, ts))
