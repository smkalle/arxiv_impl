"""
EvolveMem TicketMind API — FastAPI :8001
POST /diagnose   ticket_text → top-k KB article recommendations
GET  /health     service status + config version
GET  /metrics    request count + latency stats
GET  /loops      all four loop states (dashboard polling)
POST /loops/run  start loop_runner (background)
"""
from __future__ import annotations

import json
import subprocess
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── Ensure project root is importable ────────────────────────────────────────
sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
from loops.action_space import RetrievalConfig


# ── Request / response models ─────────────────────────────────────────────────

class DiagnoseRequest(BaseModel):
    ticket_text: str
    top_k: int = 5


class DiagnoseResponse(BaseModel):
    results: list[dict[str, Any]]
    latency_ms: int
    config_version: str


# ── App factory ───────────────────────────────────────────────────────────────

def create_app() -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Build router + ingest KB
        from simplemem_router import SimplememRouter
        from ingestor import KBIngestor, IngestorConfig

        class _Settings:
            simplemem_use_stub = cfg.SIMPLEMEM_USE_STUB
            lancedb_uri = str(cfg.LANCEDB_DIR)
            diagnosis_llm_provider = cfg.DIAGNOSIS_LLM_PROVIDER
            diagnosis_llm_model = cfg.ANTHROPIC_MODEL
            anthropic_api_key = cfg.ANTHROPIC_API_KEY
            ollama_host = cfg.OLLAMA_URL
            data_dir = str(cfg.DATA_DIR)

        settings = _Settings()
        router = SimplememRouter(settings)
        router.create("text")

        # Load evolved ingestor config if available
        if cfg.EVOLVED_INGESTOR_CONFIG.exists():
            ingestor_cfg = IngestorConfig.from_dict(
                json.loads(cfg.EVOLVED_INGESTOR_CONFIG.read_text())
            )
        else:
            ingestor_cfg = IngestorConfig()

        ingestor = KBIngestor(router, ingestor_cfg)
        ingestor.ingest_csv(cfg.KB_ARTICLES_CSV)
        ingestor.finalize()

        # Load evolved retrieval config
        if cfg.EVOLVED_RETRIEVAL_CONFIG.exists():
            retrieval_cfg = RetrievalConfig.load(cfg.EVOLVED_RETRIEVAL_CONFIG)
            config_version = "evolved"
        else:
            retrieval_cfg = RetrievalConfig()
            config_version = "baseline"

        app.state.router = router
        app.state.retrieval_config = retrieval_cfg
        app.state.config_version = config_version
        app.state.metrics = {"total": 0, "latency_total_ms": 0}

        yield

    app = FastAPI(
        title="EvolveMem TicketMind API",
        version="2.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ── Endpoints ────────────────────────────────────────────────────────────

    @app.post("/diagnose", response_model=DiagnoseResponse)
    async def diagnose(req: DiagnoseRequest, request: Request):
        if not req.ticket_text.strip():
            raise HTTPException(status_code=422, detail="ticket_text cannot be empty")

        config = request.app.state.retrieval_config
        if req.top_k != config.top_k:
            config = config.apply_patch({"top_k": req.top_k})

        t0 = time.perf_counter()
        results = request.app.state.router.ask(
            query=req.ticket_text,
            config=config,
        )
        latency_ms = int((time.perf_counter() - t0) * 1000)

        m = request.app.state.metrics
        m["total"] += 1
        m["latency_total_ms"] += latency_ms

        return DiagnoseResponse(
            results=results,
            latency_ms=latency_ms,
            config_version=request.app.state.config_version,
        )

    @app.get("/health")
    async def health(request: Request):
        loops_complete = sum(
            1
            for p in [cfg.L1_STATE, cfg.L2_STATE, cfg.L3_STATE, cfg.L4_STATE]
            if p.exists()
            and json.loads(p.read_text()).get("status") == "complete"
        )
        return {
            "status": "ok",
            "config_version": request.app.state.config_version,
            "simplemem": "stub" if cfg.SIMPLEMEM_USE_STUB else "real",
            "lancedb": "ok",
            "loops_complete": loops_complete,
        }

    @app.get("/metrics")
    async def metrics(request: Request):
        m = request.app.state.metrics
        total = m["total"]
        avg = m["latency_total_ms"] / total if total else 0.0
        return {
            "total_requests": total,
            "avg_latency_ms": round(avg, 2),
            "total_latency_ms": m["latency_total_ms"],
        }

    @app.get("/loops")
    async def loop_states():
        states = {}
        for lid, path in [
            ("L1", cfg.L1_STATE),
            ("L2", cfg.L2_STATE),
            ("L3", cfg.L3_STATE),
            ("L4", cfg.L4_STATE),
        ]:
            if path.exists():
                try:
                    states[lid] = json.loads(path.read_text())
                except json.JSONDecodeError:
                    states[lid] = {"status": "error"}
            else:
                states[lid] = {"status": "idle", "loop_id": lid}
        return states

    @app.post("/loops/run")
    async def run_loops(only: str | None = None, start_from: str = "L1"):
        """Start loop_runner.py in a subprocess (non-blocking)."""
        cmd = [sys.executable, str(Path(__file__).parent / "loops" / "loop_runner.py")]
        if only:
            cmd += ["--only", only]
        else:
            cmd += ["--from", start_from]
        subprocess.Popen(cmd, cwd=str(Path(__file__).parent))
        return {"started": True, "cmd": " ".join(cmd)}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "api:app",
        host=cfg.API_HOST,
        port=cfg.API_PORT,
        reload=False,
    )
