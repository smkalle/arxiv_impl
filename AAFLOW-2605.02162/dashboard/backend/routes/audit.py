"""Audit log routes."""
from __future__ import annotations

import json
from typing import Optional

from fastapi import APIRouter, Depends, Query

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import require_role, _get_current_user
from database import get_conn
from schemas import AuditEntry, AuditPage

router = APIRouter(prefix="/api/audit", tags=["audit"])


def _row_to_entry(row) -> AuditEntry:
    d = dict(row)
    if d.get("detail") and isinstance(d["detail"], str):
        try:
            d["detail"] = json.loads(d["detail"])
        except Exception:
            pass
    return AuditEntry(**{k: v for k, v in d.items() if k in AuditEntry.model_fields})


@router.get("", response_model=AuditPage)
async def list_audit(
    username: Optional[str] = Query(None),
    action: Optional[str] = Query(None),
    date_from: Optional[str] = Query(None),
    date_to: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=200),
    user=Depends(_get_current_user),
):
    # Ops can only see their own actions
    role = user.get("role")
    filters = ["1=1"]
    params = []

    if role == "ops":
        filters.append("username=?")
        params.append(user["sub"])
    elif username:
        filters.append("username=?")
        params.append(username)

    if action:
        filters.append("action LIKE ?")
        params.append(f"%{action}%")
    if date_from:
        filters.append("recorded_at >= ?")
        params.append(date_from)
    if date_to:
        filters.append("recorded_at <= ?")
        params.append(date_to)

    where = " AND ".join(filters)
    conn = get_conn()
    total = conn.execute(f"SELECT COUNT(*) FROM audit_log WHERE {where}", params).fetchone()[0]
    offset = (page - 1) * limit
    rows = conn.execute(
        f"SELECT * FROM audit_log WHERE {where} ORDER BY recorded_at DESC LIMIT ? OFFSET ?",
        params + [limit, offset],
    ).fetchall()
    conn.close()

    return AuditPage(
        items=[_row_to_entry(r) for r in rows],
        total=total,
        page=page,
        limit=limit,
    )
