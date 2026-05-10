import json
import os
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from src.enrich import DEFAULT_MODEL, OLLAMA_HOST, enrich_article, enrich_corpus
from src.index import read_jsonl
import src.retrieve as retrieve_module

app = FastAPI(title="SIRA Enrichment Monitor")

# Static files & templates
app.mount("/static", StaticFiles(directory="src/static"), name="static")
templates = Jinja2Templates(directory="src/templates")

DATA_DIR = Path("data")
CORPUS_PATH = DATA_DIR / "kb_corpus.jsonl"
ENRICHED_PATH = DATA_DIR / "enriched_corpus.jsonl"
INDEX_PATH = DATA_DIR / "bm25_index.pkl"

MODEL_CATALOG = {
    "qwen2.5:3b": {"size_label": "~1.9GB", "pull": "ollama pull qwen2.5:3b"},
    "qwen3:1.7b": {"size_label": "~2.5GB", "pull": "ollama pull qwen3:1.7b"},
    "llama3.2:3b": {"size_label": "~3.5GB", "pull": "ollama pull llama3.2:3b"},
    "gemma3:1b": {"size_label": "~1.5GB", "pull": "ollama pull gemma3:1b"},
    "phi4-mini": {"size_label": "~2.5GB", "pull": "ollama pull phi4-mini"},
    "phi3:mini": {"size_label": "~2.3GB", "pull": "ollama pull phi3:mini"},
    "deepseek-r1:1.5b": {"size_label": "~1.5GB", "pull": "ollama pull deepseek-r1:1.5b"},
}
ALLOWED_MODELS = set(MODEL_CATALOG.keys())


def _canonical_model_name(model_name: str) -> str:
    name = model_name.strip()
    if name.endswith(":latest"):
        return name[: -len(":latest")]
    return name

MODEL_STATE = {
    "active_enrich_model": DEFAULT_MODEL,
    "active_sketch_model": DEFAULT_MODEL,
    "previous_models": [],
    "last_switch_at": None,
    "last_switch_error": None,
}
MODEL_SWITCH_LOCK = threading.Lock()
LOG_BUFFER_LOCK = threading.Lock()
LOG_BUFFER_MAX = 500
LOG_BUFFER: list[dict] = []
LOG_CURSOR = 0


def _append_log(category: str, message: str, level: str = "info", meta: dict | None = None) -> None:
    global LOG_CURSOR
    with LOG_BUFFER_LOCK:
        LOG_CURSOR += 1
        LOG_BUFFER.append({
            "id": LOG_CURSOR,
            "ts": datetime.now(timezone.utc).isoformat(),
            "category": category,
            "level": level,
            "message": message,
            "meta": meta or {},
        })
        if len(LOG_BUFFER) > LOG_BUFFER_MAX:
            del LOG_BUFFER[: len(LOG_BUFFER) - LOG_BUFFER_MAX]


def _is_allowed_model(model_name: str) -> tuple[bool, str]:
    canonical = _canonical_model_name(model_name)
    if canonical in ALLOWED_MODELS:
        return True, "allowed"
    if canonical == "qwen3:4b":
        return False, "excluded_qwen3_4b"
    return False, "not_in_allowlist"


def _list_installed_models() -> list[dict]:
    try:
        import ollama
    except Exception:
        return []
    try:
        client = ollama.Client(host=OLLAMA_HOST)
        data = client.list()
    except Exception:
        data = {}
    models = []
    for m in data.get("models", []):
        name = m.get("name")
        if not name:
            continue
        allowed, reason = _is_allowed_model(name)
        models.append({
            "name": name,
            "canonical_name": _canonical_model_name(name),
            "size": m.get("size"),
            "allowed": allowed,
            "reason": reason,
            "size_label": MODEL_CATALOG.get(_canonical_model_name(name), {}).get("size_label"),
            "pull": MODEL_CATALOG.get(_canonical_model_name(name), {}).get("pull"),
        })

    if not models:
        try:
            out = subprocess.run(["ollama", "list"], capture_output=True, text=True, check=True)
            lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
            for ln in lines[1:]:
                parts = ln.split()
                if not parts:
                    continue
                name = parts[0]
                allowed, reason = _is_allowed_model(name)
                models.append({
                    "name": name,
                    "canonical_name": _canonical_model_name(name),
                    "size": None,
                    "allowed": allowed,
                    "reason": reason,
                    "size_label": MODEL_CATALOG.get(_canonical_model_name(name), {}).get("size_label"),
                    "pull": MODEL_CATALOG.get(_canonical_model_name(name), {}).get("pull"),
                })
        except Exception:
            pass

    return models


def _format_timestamp_for_display(value: str | None) -> str:
    if not value:
        return "—"
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return dt.astimezone().strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return value


def _prepare_articles_for_display(articles: list[dict]) -> list[dict]:
    prepared = []
    for a in articles:
        item = dict(a)
        item["last_updated_display"] = _format_timestamp_for_display(a.get("last_updated"))
        prepared.append(item)
    return prepared


def _unload_model(model_name: str) -> tuple[bool, str]:
    try:
        import ollama
        client = ollama.Client(host=OLLAMA_HOST)
        client.generate(model=model_name, prompt="", keep_alive=0)
        return True, "unloaded"
    except Exception as exc:
        return False, str(exc)


def _try_load_index() -> bool:
    """Attempt to load the BM25 index; return True on success."""
    if retrieve_module._index is not None:
        return True
    if INDEX_PATH.exists():
        try:
            retrieve_module.load_index(INDEX_PATH)
            return True
        except Exception:
            pass
    return False


@app.on_event("startup")
async def startup_load_index():
    ok = _try_load_index()
    _append_log("system", "UI server startup", meta={"index_loaded": ok})


def _load_corpus(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return read_jsonl(path)


def _compute_stats(articles: list[dict]) -> dict:
    enriched = [a for a in articles if a.get("enriched_at")]
    avg_terms = round(sum(len(a.get("enriched_terms", [])) for a in enriched) / max(len(enriched), 1), 1)
    model = enriched[0].get("model_used", DEFAULT_MODEL) if enriched else DEFAULT_MODEL
    last_run = None
    if enriched:
        last_run = max(a["enriched_at"] for a in enriched)
    return {
        "total": len(articles),
        "enriched": len(enriched),
        "avg_terms": avg_terms,
        "model": model,
        "last_run": last_run,
    }


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    articles = _load_corpus(ENRICHED_PATH)
    if not articles:
        articles = _load_corpus(CORPUS_PATH)
    articles = _prepare_articles_for_display(articles)
    stats = _compute_stats(articles)
    return templates.TemplateResponse("enrich_ui.html", {
        "request": request,
        "articles": articles,
        "stats": stats,
        "api_url": os.getenv("SIRA_API_URL", "http://localhost:8001"),
    })


@app.post("/api/enrich/{article_id}")
async def enrich_single(article_id: str):
    articles = _load_corpus(CORPUS_PATH)
    article = next((a for a in articles if a["article_id"] == article_id), None)
    if not article:
        _append_log("enrich", f"enrich_single not found: {article_id}", level="error")
        return {"error": f"Article {article_id} not found"}

    try:
        telemetry = {}
        result = enrich_article(
            article,
            telemetry=telemetry,
            model=MODEL_STATE["active_enrich_model"],
        )
        _append_log(
            "enrich",
            f"enriched article {article_id}",
            meta={
                "model": MODEL_STATE["active_enrich_model"],
                "terms": len(result.get("enriched_terms", [])),
                "duration_sec": telemetry.get("duration_sec"),
            },
        )
        # Merge back into enriched corpus
        enriched = _load_corpus(ENRICHED_PATH)
        idx = next((i for i, a in enumerate(enriched) if a["article_id"] == article_id), None)
        if idx is not None:
            enriched[idx] = result
        else:
            enriched.append(result)
        with open(ENRICHED_PATH, "w") as f:
            for a in enriched:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")
        return {"success": True, "article": result}
    except Exception as exc:
        _append_log("enrich", f"enrich_single failed: {article_id}", level="error", meta={"error": str(exc)})
        return {"error": str(exc)}


@app.get("/api/enrich/all")
async def enrich_all():
    articles = _load_corpus(CORPUS_PATH)
    total = len(articles)

    async def event_generator():
        enriched = []
        failed = 0
        _append_log("enrich", "enrich_all started", meta={"total": total, "model": MODEL_STATE["active_enrich_model"]})
        for i, art in enumerate(articles):
            aid = art["article_id"]
            try:
                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total, 'article_id': aid, 'status': 'enriching'})}\n\n"
                telemetry = {}
                result = enrich_article(
                    art,
                    telemetry=telemetry,
                    model=MODEL_STATE["active_enrich_model"],
                )
                enriched.append(result)
                _append_log(
                    "enrich",
                    f"enriched {aid}",
                    meta={"current": i + 1, "total": total, "terms": len(result.get("enriched_terms", []))},
                )
                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total, 'article_id': aid, 'status': 'done', 'terms': len(result.get('enriched_terms', []))})}\n\n"
            except Exception as exc:
                enriched.append(art)
                failed += 1
                _append_log("enrich", f"failed {aid}", level="error", meta={"error": str(exc), "current": i + 1, "total": total})
                yield f"data: {json.dumps({'type': 'progress', 'current': i + 1, 'total': total, 'article_id': aid, 'status': 'failed', 'error': str(exc)})}\n\n"

        with open(ENRICHED_PATH, "w") as f:
            for a in enriched:
                f.write(json.dumps(a, ensure_ascii=False) + "\n")

        yield f"data: {json.dumps({'type': 'complete', 'total': total, 'enriched': total - failed, 'failed': failed})}\n\n"
        _append_log("enrich", "enrich_all complete", meta={"total": total, "enriched": total - failed, "failed": failed})

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/api/articles")
async def list_articles():
    articles = _load_corpus(ENRICHED_PATH)
    if not articles:
        articles = _load_corpus(CORPUS_PATH)
    articles = _prepare_articles_for_display(articles)
    return {"articles": articles, "stats": _compute_stats(articles)}


@app.get("/api/models")
async def api_models():
    installed_models = _list_installed_models()
    installed_canonical_names = {_canonical_model_name(m["name"]) for m in installed_models}

    missing = []
    for name in ALLOWED_MODELS:
        if name not in installed_canonical_names:
            missing.append({
                "name": name,
                "canonical_name": name,
                "size": None,
                "allowed": True,
                "reason": "not_installed",
                "size_label": MODEL_CATALOG.get(name, {}).get("size_label"),
                "pull": MODEL_CATALOG.get(name, {}).get("pull"),
            })

    return {
        "installed": [m for m in installed_models if m["allowed"]],
        "missing": sorted(missing, key=lambda x: x["name"]),
        "rejected": [m for m in installed_models if not m["allowed"]],
    }


@app.get("/api/models/current")
async def api_models_current():
    return MODEL_STATE


@app.post("/api/models/select")
async def api_models_select(request: Request):
    body = await request.json()
    model = (body.get("model") or "").strip()
    apply_to = body.get("apply_to") or []

    if not model:
        return JSONResponse({"error": "model is required"}, status_code=400)
    if not isinstance(apply_to, list) or not apply_to:
        return JSONResponse({"error": "apply_to must be non-empty list: ['enrich','sketch']"}, status_code=400)

    models = _list_installed_models()
    allowed_names = {m["name"] for m in models if m["allowed"]}
    if model not in allowed_names:
        return JSONResponse({"error": f"model not allowed or not installed: {model}"}, status_code=400)

    with MODEL_SWITCH_LOCK:
        prev = set()
        if "enrich" in apply_to:
            prev.add(MODEL_STATE["active_enrich_model"])
            MODEL_STATE["active_enrich_model"] = model
        if "sketch" in apply_to:
            prev.add(MODEL_STATE["active_sketch_model"])
            MODEL_STATE["active_sketch_model"] = model

        MODEL_STATE["previous_models"] = [p for p in prev if p and p != model]
        MODEL_STATE["last_switch_at"] = datetime.now(timezone.utc).isoformat()
        MODEL_STATE["last_switch_error"] = None

        unload_results = []
        for old_model in MODEL_STATE["previous_models"]:
            ok, msg = _unload_model(old_model)
            unload_results.append({"model": old_model, "ok": ok, "message": msg})
            if not ok:
                MODEL_STATE["last_switch_error"] = f"failed to unload {old_model}: {msg}"

    _append_log(
        "models",
        f"model switched to {model}",
        meta={"apply_to": apply_to, "unload_results": unload_results},
    )

    return {
        "ok": True,
        "state": MODEL_STATE,
        "unload_results": unload_results,
    }


@app.post("/api/models/unload")
async def api_models_unload(request: Request):
    body = await request.json() if request.headers.get("content-type", "").startswith("application/json") else {}
    model = (body.get("model") or "").strip() if isinstance(body, dict) else ""
    targets = [model] if model else list(MODEL_STATE.get("previous_models", []))
    if not targets:
        return {"ok": True, "unload_results": []}

    results = []
    for m in targets:
        ok, msg = _unload_model(m)
        results.append({"model": m, "ok": ok, "message": msg})
    _append_log("models", "manual unload requested", meta={"targets": targets, "results": results})
    return {"ok": True, "unload_results": results}


@app.get("/api/monitor")
async def api_monitor():
    index_loaded = _try_load_index()
    corpus_size = len(retrieve_module._index.articles) if retrieve_module._index else 0
    return {
        "health": {
            "bm25_index_loaded": index_loaded,
            "corpus_size": corpus_size,
            "index_built_at": datetime.fromtimestamp(INDEX_PATH.stat().st_mtime, tz=timezone.utc).isoformat() if INDEX_PATH.exists() else None,
        },
        "models": MODEL_STATE,
        "ollama_host": OLLAMA_HOST,
    }


@app.get("/api/logs")
async def api_logs(since: int = 0):
    with LOG_BUFFER_LOCK:
        entries = [e for e in LOG_BUFFER if e["id"] > since]
        next_id = LOG_CURSOR
    return {"entries": entries, "next_id": next_id}


# ---------------------------------------------------------------------------
# Iteration 3 — SIRA Query UI
# ---------------------------------------------------------------------------

@app.get("/query", response_class=HTMLResponse)
async def query_page(request: Request):
    index_loaded = _try_load_index()
    corpus_size = len(retrieve_module._index.articles) if retrieve_module._index else 0
    return templates.TemplateResponse("query_ui.html", {
        "request": request,
        "index_loaded": index_loaded,
        "corpus_size": corpus_size,
        "active_sketch_model": MODEL_STATE["active_sketch_model"],
    })


@app.post("/api/query")
async def api_query(request: Request):
    body = await request.json()
    ticket_text = (body.get("ticket_text") or "").strip()[:4000]
    mode = body.get("mode", "sira")          # "sira" | "plain"
    top_k = int(body.get("top_k", 5))
    tau = float(body.get("tau", 0.01))
    weight = float(body.get("weight", 1.5))

    if not ticket_text:
        _append_log("query", "query rejected: missing ticket_text", level="error")
        return JSONResponse({"error": "ticket_text is required"}, status_code=400)

    if not _try_load_index():
        _append_log("system", "query failed: index not loaded", level="error")
        return JSONResponse({"error": "Index not loaded. Build it first with: python3 src/index.py data/enriched_corpus.jsonl --output data/bm25_index.pkl"}, status_code=503)

    try:
        if mode == "plain":
            results = retrieve_module.retrieve(ticket_text, top_k=top_k)
            _append_log("query", "plain query", meta={"top_k": top_k, "results": len(results)})
            return {
                "mode": "plain",
                "results": results,
                "sketch_terms_generated": [],
                "sketch_terms_validated": [],
                "sketch_terms_rejected": [],
                "fallback_used": False,
                "hallucination_rate": 0.0,
                "latency_ms": None,
            }
        else:
            response = retrieve_module.sira_retrieve(
                ticket_text,
                top_k=top_k,
                w=weight,
                tau=tau,
                sketch_model=MODEL_STATE["active_sketch_model"],
            )
            response["mode"] = "sira"
            response["sketch_model"] = MODEL_STATE["active_sketch_model"]
            _append_log(
                "query",
                "sira query",
                meta={
                    "top_k": top_k,
                    "tau": tau,
                    "weight": weight,
                    "sketch_model": MODEL_STATE["active_sketch_model"],
                    "fallback_used": response.get("fallback_used"),
                    "latency_ms": response.get("latency_ms"),
                    "validated": len(response.get("sketch_terms_validated", [])),
                },
            )
            return response
    except Exception as exc:
        _append_log("query", "query error", level="error", meta={"error": str(exc)})
        return JSONResponse({"error": str(exc)}, status_code=500)
