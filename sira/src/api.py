import json
import logging
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException

import src.retrieve as retrieve_module
from src.models import (
    FeedbackRequest,
    FeedbackResponse,
    HealthResponse,
    RetrieveRequest,
    RetrieveResponse,
)

logger = logging.getLogger(__name__)

app = FastAPI(title="SIRA Retrieval API")

DATA_DIR = Path("data")
INDEX_PATH = DATA_DIR / "bm25_index.pkl"
FEEDBACK_PATH = DATA_DIR / "feedback.jsonl"


def _try_load_index() -> bool:
    if retrieve_module._index is not None:
        return True
    if INDEX_PATH.exists():
        try:
            retrieve_module.load_index(INDEX_PATH)
            return True
        except Exception as exc:
            logger.warning("Failed to load index: %s", exc)
    return False


def _index_built_at() -> str | None:
    if not INDEX_PATH.exists():
        return None
    ts = datetime.fromtimestamp(INDEX_PATH.stat().st_mtime, tz=timezone.utc)
    return ts.isoformat()


@app.on_event("startup")
async def startup_load_index() -> None:
    _try_load_index()


@app.get("/health", response_model=HealthResponse)
async def health() -> HealthResponse:
    loaded = retrieve_module._index is not None and retrieve_module._index.bm25 is not None
    corpus_size = len(retrieve_module._index.articles) if loaded else 0
    return HealthResponse(
        bm25_index_loaded=loaded,
        corpus_size=corpus_size,
        index_built_at=_index_built_at(),
    )


@app.post("/retrieve", response_model=RetrieveResponse)
async def retrieve(req: RetrieveRequest) -> RetrieveResponse:
    if not _try_load_index():
        raise HTTPException(
            status_code=503,
            detail="Index not loaded. Build it first with: PYTHONPATH=. python3 -c \"from src.index import build_and_save; build_and_save('data/enriched_corpus.jsonl','data/bm25_index.pkl')\"",
        )

    warning = None
    ticket_text = req.ticket_text
    if len(ticket_text) > 4000:
        ticket_text = ticket_text[:4000]
        warning = "ticket_text truncated to 4000 characters"

    response = retrieve_module.sira_retrieve(
        ticket_text,
        top_k=req.top_k,
        w=req.weight,
        tau=req.tau,
    )

    logger.info(
        "retrieve ticket_id=%s fallback=%s latency_ms=%s generated=%d validated=%d rejected=%d",
        req.ticket_id,
        response.get("fallback_used"),
        response.get("latency_ms"),
        len(response.get("sketch_terms_generated", [])),
        len(response.get("sketch_terms_validated", [])),
        len(response.get("sketch_terms_rejected", [])),
    )

    response["warning"] = warning
    return RetrieveResponse(**response)


@app.post("/feedback", response_model=FeedbackResponse)
async def feedback(req: FeedbackRequest) -> FeedbackResponse:
    FEEDBACK_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "ticket_id": req.ticket_id,
        "selected_article_id": req.selected_article_id,
        "rating": req.rating,
        "comments": req.comments,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with open(FEEDBACK_PATH, "a") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return FeedbackResponse(ok=True, message="feedback recorded")
