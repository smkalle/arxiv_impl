"""FastAPI retrieval API."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.evolution import load_state, run_evolution
from src.retrieve import evolved_retrieve, load_index, retrieve
from src.session_store import end_session, list_sessions, record_event, start_session


INDEX_PATH = Path("data/bm25_index.pkl")
app = FastAPI(title="TicketMind API", version="0.1.0")


class QueryRequest(BaseModel):
    ticket: str = Field(..., min_length=1)
    top_k: int = Field(5, ge=1, le=20)
    use_evolved: bool = True
    use_sira: bool | None = None
    tau: float = 0.01
    weight: float = 1.5


class SessionStart(BaseModel):
    customer_id: str = Field(..., min_length=1)


class SessionRecord(BaseModel):
    text: str = Field(..., min_length=1)


def ensure_loaded() -> None:
    if not INDEX_PATH.exists():
        raise HTTPException(status_code=503, detail="BM25 index is missing; build it first")
    load_index(INDEX_PATH)


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok" if INDEX_PATH.exists() else "missing_index",
        "config_version": "local-v1",
        "index_path": str(INDEX_PATH),
        "evolution": load_state(),
    }


@app.post("/query")
def query(request: QueryRequest) -> dict[str, Any]:
    start = time.perf_counter()
    ensure_loaded()
    use_evolved = request.use_evolved if request.use_sira is None else request.use_sira
    if use_evolved:
        payload = evolved_retrieve(request.ticket, top_k=request.top_k, tau=request.tau, weight=request.weight)
        results = payload["results"]
        trace = payload["trace"]
        fallback_used = payload["fallback_used"]
    else:
        results = retrieve(request.ticket, top_k=request.top_k)
        trace = {"plain_tokens": request.ticket.split()}
        fallback_used = False
    return {
        "results": results,
        "latency_ms": round((time.perf_counter() - start) * 1000, 2),
        "fallback_used": fallback_used,
        "trace": trace,
    }


@app.post("/session/start")
def api_start_session(request: SessionStart) -> dict[str, Any]:
    return start_session(request.customer_id)


@app.post("/session/{session_id}/record")
def api_record_session(session_id: str, request: SessionRecord) -> dict[str, Any]:
    try:
        return record_event(session_id, request.text)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.post("/session/{session_id}/end")
def api_end_session(session_id: str) -> dict[str, Any]:
    try:
        return end_session(session_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="session not found") from exc


@app.get("/sessions")
def api_sessions() -> dict[str, Any]:
    return {"sessions": list_sessions()}


@app.post("/evolution/start")
def api_evolution_start() -> dict[str, Any]:
    return run_evolution()
