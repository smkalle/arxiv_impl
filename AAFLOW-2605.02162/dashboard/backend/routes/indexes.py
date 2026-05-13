"""Index health routes."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import require_admin, require_any, require_ops_or_admin
from database import get_conn, _lock
from schemas import IndexOut, IndexesPage

router = APIRouter(prefix="/api/indexes", tags=["indexes"])


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_index(row, runs=None) -> IndexOut:
    d = dict(row)
    idx = IndexOut(**{k: v for k, v in d.items() if k in IndexOut.model_fields})
    if runs is not None:
        from routes.runs import _row_to_run
        idx.runs = [_row_to_run(r) for r in runs]
    return idx


@router.get("", response_model=IndexesPage)
async def list_indexes(user=Depends(require_any)):
    conn = get_conn()
    rows = conn.execute(
        "SELECT * FROM indexes WHERE soft_deleted=0 ORDER BY last_updated DESC"
    ).fetchall()
    conn.close()
    return IndexesPage(items=[_row_to_index(r) for r in rows], total=len(rows))


@router.get("/{name}", response_model=IndexOut)
async def get_index(name: str, user=Depends(require_any)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM indexes WHERE index_name=?", (name,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "INDEX_NOT_FOUND", "message": f"Index {name} not found"})
    if row["soft_deleted"]:
        conn.close()
        raise HTTPException(410, {"code": "INDEX_SOFT_DELETED", "message": f"Index {name} is deleted"})
    runs = conn.execute(
        "SELECT * FROM runs WHERE index_name=? ORDER BY queued_at DESC LIMIT 20", (name,)
    ).fetchall()
    conn.close()
    return _row_to_index(row, runs)


@router.post("/{name}/check-consistency")
async def check_consistency(name: str, user=Depends(require_admin)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM indexes WHERE index_name=?", (name,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "INDEX_NOT_FOUND", "message": f"Index {name} not found"})

    # Simulate a consistency check
    result = "ok"
    now_str = _iso(_now())
    with _lock:
        conn.execute(
            "UPDATE indexes SET consistency_status=?, consistency_checked_at=? WHERE index_name=?",
            (result, now_str, name),
        )
        conn.commit()
    conn.close()
    return {"index_name": name, "consistency_status": result, "checked_at": now_str}


@router.get("/{name}/artifacts")
async def get_artifacts(name: str, user=Depends(require_ops_or_admin)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM indexes WHERE index_name=?", (name,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(404, {"code": "INDEX_NOT_FOUND", "message": f"Index {name} not found"})

    # Return "signed" (simulated) download URLs
    base = f"/api/indexes/{name}/download"
    return {
        "tickets_arrow": f"{base}/tickets.arrow",
        "index_faiss": f"{base}/index.faiss",
        "run_summary": f"{base}/run_summary.json",
    }


@router.delete("/{name}")
async def delete_index(
    name: str,
    request: Request,
    user=Depends(require_admin),
):
    confirm = request.headers.get("X-Confirm-Index-Name")
    if confirm != name:
        raise HTTPException(400, {"code": "CONFIRM_HEADER_MISSING",
                                  "message": "Set X-Confirm-Index-Name header to the index name"})

    conn = get_conn()
    row = conn.execute("SELECT * FROM indexes WHERE index_name=?", (name,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "INDEX_NOT_FOUND", "message": f"Index {name} not found"})

    now_str = _iso(_now())
    with _lock:
        conn.execute(
            "UPDATE indexes SET soft_deleted=1, soft_deleted_at=?, soft_deleted_by=? WHERE index_name=?",
            (now_str, user["sub"], name),
        )
        conn.execute("""
            INSERT INTO audit_log (username, action, target_type, target_id, detail, ip_address, recorded_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user["sub"], "index.delete", "index", name,
              json.dumps({"index_name": name}),
              str(request.client.host) if request.client else None,
              now_str))
        conn.commit()
    conn.close()
    return {"status": "soft_deleted", "index_name": name, "deleted_at": now_str}


@router.post("/{name}/restore")
async def restore_index(name: str, user=Depends(require_admin)):
    from datetime import timedelta
    conn = get_conn()
    row = conn.execute("SELECT * FROM indexes WHERE index_name=?", (name,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "INDEX_NOT_FOUND", "message": f"Index {name} not found"})

    if not row["soft_deleted"]:
        conn.close()
        return {"status": "not_deleted", "index_name": name}

    # Check 30-second undo window
    if row["soft_deleted_at"]:
        deleted_at = datetime.fromisoformat(row["soft_deleted_at"].replace("Z", "+00:00"))
        if (_now() - deleted_at).total_seconds() > 30:
            conn.close()
            raise HTTPException(409, {"code": "UNDO_WINDOW_EXPIRED",
                                      "message": "30-second undo window has expired"})

    with _lock:
        conn.execute(
            "UPDATE indexes SET soft_deleted=0, soft_deleted_at=NULL, soft_deleted_by=NULL WHERE index_name=?",
            (name,),
        )
        conn.commit()
    conn.close()
    return {"status": "restored", "index_name": name}
