"""
EvolveMem TicketMind Dashboard — FastAPI + Jinja2 + HTMX :8000
Serves the four-loop AutoResearch monitor from the provided HTML design.
"""
from __future__ import annotations

import csv
import json
import sys
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

sys.path.insert(0, str(Path(__file__).parent))
import config as cfg

TEMPLATES_DIR = Path(__file__).parent / "templates"


def _load_loop_states() -> dict[str, Any]:
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
                states[lid] = {"status": "error", "loop_id": lid}
        else:
            states[lid] = {
                "status": "idle", "loop_id": lid,
                "rounds_done": 0, "max_rounds": 0,
                "best_fitness": 0.0, "baseline_fitness": 0.0,
                "fitness_history": [],
            }
    return states


def _load_kb_articles(limit: int = 50) -> list[dict[str, Any]]:
    articles = []
    if not cfg.KB_ARTICLES_CSV.exists():
        return articles
    with open(cfg.KB_ARTICLES_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if i >= limit:
                break
            articles.append(row)
    return articles


def _load_failure_log(limit: int = 100) -> list[dict[str, Any]]:
    entries = []
    if not cfg.FAILURE_LOG_JSONL.exists():
        return entries
    with open(cfg.FAILURE_LOG_JSONL) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries[-limit:]


def _any_running(states: dict[str, Any]) -> bool:
    return any(s.get("status") == "running" for s in states.values())


def create_app() -> FastAPI:

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        yield

    app = FastAPI(title="EvolveMem Dashboard", version="2.0", lifespan=lifespan)
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # ── Pages ────────────────────────────────────────────────────────────────

    @app.get("/", response_class=HTMLResponse)
    @app.get("/loops", response_class=HTMLResponse)
    async def loops_page(request: Request):
        states = _load_loop_states()
        return templates.TemplateResponse("loops.html", {
            "request": request,
            "loop_states": states,
            "any_running": _any_running(states),
            "page": "loops",
        })

    @app.get("/kb", response_class=HTMLResponse)
    async def kb_page(request: Request):
        articles = _load_kb_articles()
        return templates.TemplateResponse("kb.html", {
            "request": request,
            "articles": articles,
            "total": len(articles),
            "page": "kb",
        })

    @app.get("/query", response_class=HTMLResponse)
    async def query_page(request: Request):
        return templates.TemplateResponse("query.html", {
            "request": request,
            "page": "query",
            "api_url": f"http://localhost:{cfg.API_PORT}",
        })

    @app.get("/sessions", response_class=HTMLResponse)
    async def sessions_page(request: Request):
        log = _load_failure_log()
        return templates.TemplateResponse("sessions.html", {
            "request": request,
            "log_entries": log,
            "page": "sessions",
        })

    @app.get("/system", response_class=HTMLResponse)
    async def system_page(request: Request):
        import platform
        states = _load_loop_states()
        return templates.TemplateResponse("system.html", {
            "request": request,
            "page": "system",
            "python_version": platform.python_version(),
            "platform": platform.machine(),
            "simplemem_mode": "stub" if cfg.SIMPLEMEM_USE_STUB else "real",
            "llm_provider": cfg.DIAGNOSIS_LLM_PROVIDER,
            "loop_states": states,
            "lancedb_dir": str(cfg.LANCEDB_DIR),
        })

    # ── HTMX partials (polled every 5s) ──────────────────────────────────────

    @app.get("/partials/loop-states", response_class=HTMLResponse)
    async def loop_states_partial(request: Request):
        states = _load_loop_states()
        return templates.TemplateResponse("partials/loop_states.html", {
            "request": request,
            "loop_states": states,
            "any_running": _any_running(states),
        })

    @app.get("/health")
    async def health():
        return {"status": "ok", "ts": time.time()}

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "dashboard:app",
        host=cfg.DASHBOARD_HOST,
        port=cfg.DASHBOARD_PORT,
        reload=False,
    )
