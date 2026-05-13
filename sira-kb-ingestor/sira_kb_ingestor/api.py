from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from time import perf_counter
from typing import Any

from fastapi import FastAPI, HTTPException, Request

from sira_kb_ingestor.errors import RetrievalError
from sira_kb_ingestor.retriever import Retriever


def create_app(artifact_dir: Path | str = "./sira-artifacts") -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.retriever._try_load()
        yield

    app = FastAPI(title="sira-kb-ingestor API", lifespan=lifespan)
    app.state.retriever = Retriever(artifact_dir)
    app.state.metrics = {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "fallback_count": 0,
        "total_latency_ms": 0,
    }

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return app.state.retriever.health()

    @app.post("/retrieve")
    async def retrieve(request: Request) -> dict[str, Any]:
        metrics = app.state.metrics
        metrics["total_requests"] += 1
        started = perf_counter()

        try:
            payload = await request.json()
        except Exception as exc:
            metrics["failed_requests"] += 1
            raise HTTPException(status_code=400, detail="Request body must be valid JSON") from exc

        ticket_text = payload.get("ticket_text")
        if not isinstance(ticket_text, str) or not ticket_text.strip():
            metrics["failed_requests"] += 1
            raise HTTPException(status_code=400, detail="ticket_text is required")

        top_k = int(payload.get("top_k", 5))
        tau = float(payload.get("tau", 0.01))
        weight = float(payload.get("weight", 1.5))

        try:
            response = app.state.retriever.retrieve(ticket_text, top_k=top_k, tau=tau, weight=weight)
        except RetrievalError as exc:
            metrics["failed_requests"] += 1
            health_payload = app.state.retriever.health()
            status_code = 503 if not health_payload.get("bm25_index_loaded") else 500
            raise HTTPException(status_code=status_code, detail=str(exc)) from exc
        except Exception as exc:
            metrics["failed_requests"] += 1
            raise HTTPException(status_code=500, detail=f"Unexpected retrieval error: {exc}") from exc

        elapsed_ms = int((perf_counter() - started) * 1000)
        metrics["successful_requests"] += 1
        metrics["total_latency_ms"] += elapsed_ms
        if response.get("audit", {}).get("fallback_used"):
            metrics["fallback_count"] += 1
        return response

    @app.get("/metrics")
    async def metrics() -> dict[str, Any]:
        payload = dict(app.state.metrics)
        successful = payload["successful_requests"]
        payload["average_latency_ms"] = (
            round(payload["total_latency_ms"] / successful, 2) if successful else 0.0
        )
        return payload

    return app


app = create_app()
