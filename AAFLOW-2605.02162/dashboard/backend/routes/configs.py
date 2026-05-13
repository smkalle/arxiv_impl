"""Configuration CRUD routes."""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from auth import require_admin, require_any
from database import get_conn, _lock
from schemas import ConfigIn, ConfigOut

router = APIRouter(prefix="/api/configs", tags=["configs"])


def _iso(dt: datetime) -> str:
    return dt.isoformat(timespec="seconds").replace("+00:00", "Z")


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _row_to_config(row) -> ConfigOut:
    return ConfigOut(**dict(row))


@router.get("", response_model=list[ConfigOut])
async def list_configs(user=Depends(require_any)):
    conn = get_conn()
    rows = conn.execute("SELECT * FROM configs ORDER BY created_at DESC").fetchall()
    conn.close()
    return [_row_to_config(r) for r in rows]


@router.post("", response_model=ConfigOut, status_code=201)
async def create_config(body: ConfigIn, request: Request, user=Depends(require_admin)):
    config_id = f"cfg-{uuid.uuid4().hex[:8]}"
    now_str = _iso(_now())

    conn = get_conn()
    with _lock:
        conn.execute("""
            INSERT INTO configs
              (config_id, config_name, source_type, batch_size, max_workers,
               max_chunk_chars, min_chunk_chars, null_policy, faiss_factory,
               embed_model, created_by, created_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
        """, (
            config_id, body.config_name, body.source_type,
            body.batch_size, body.max_workers, body.max_chunk_chars,
            body.min_chunk_chars, body.null_policy, body.faiss_factory,
            body.embed_model, user["sub"], now_str,
        ))
        conn.execute("""
            INSERT INTO audit_log (username, action, target_type, target_id, detail, ip_address, recorded_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user["sub"], "config.create", "config", config_id,
              json.dumps(body.model_dump()),
              str(request.client.host) if request.client else None,
              now_str))
        conn.commit()

    row = conn.execute("SELECT * FROM configs WHERE config_id=?", (config_id,)).fetchone()
    conn.close()
    return _row_to_config(row)


@router.put("/{config_id}", response_model=ConfigOut)
async def update_config(config_id: str, body: ConfigIn, request: Request, user=Depends(require_admin)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM configs WHERE config_id=?", (config_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "CONFIG_NOT_FOUND", "message": f"Config {config_id} not found"})

    now_str = _iso(_now())
    with _lock:
        conn.execute("""
            UPDATE configs SET
              config_name=?, source_type=?, batch_size=?, max_workers=?,
              max_chunk_chars=?, min_chunk_chars=?, null_policy=?,
              faiss_factory=?, embed_model=?, updated_at=?
            WHERE config_id=?
        """, (
            body.config_name, body.source_type, body.batch_size, body.max_workers,
            body.max_chunk_chars, body.min_chunk_chars, body.null_policy,
            body.faiss_factory, body.embed_model, now_str, config_id,
        ))
        conn.execute("""
            INSERT INTO audit_log (username, action, target_type, target_id, detail, ip_address, recorded_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user["sub"], "config.update", "config", config_id,
              json.dumps(body.model_dump()),
              str(request.client.host) if request.client else None,
              now_str))
        conn.commit()

    row = conn.execute("SELECT * FROM configs WHERE config_id=?", (config_id,)).fetchone()
    conn.close()
    return _row_to_config(row)


@router.delete("/{config_id}")
async def delete_config(config_id: str, request: Request, user=Depends(require_admin)):
    conn = get_conn()
    row = conn.execute("SELECT * FROM configs WHERE config_id=?", (config_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(404, {"code": "CONFIG_NOT_FOUND", "message": f"Config {config_id} not found"})

    now_str = _iso(_now())
    with _lock:
        conn.execute("DELETE FROM configs WHERE config_id=?", (config_id,))
        conn.execute("""
            INSERT INTO audit_log (username, action, target_type, target_id, detail, ip_address, recorded_at)
            VALUES (?,?,?,?,?,?,?)
        """, (user["sub"], "config.delete", "config", config_id,
              json.dumps({"config_name": row["config_name"]}),
              str(request.client.host) if request.client else None,
              now_str))
        conn.commit()
    conn.close()
    return {"status": "deleted", "config_id": config_id}
