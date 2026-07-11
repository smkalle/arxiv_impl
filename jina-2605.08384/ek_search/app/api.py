"""FastAPI application — /ingest, /search, /health, /stats, /eval, /."""
from __future__ import annotations
import dataclasses
import logging
import time
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.models import (
    IngestRequest, IngestResponse,
    SearchRequest, SearchResponse, SearchResult,
    EvalReport,
)
from app.backends.factory import get_backend
from app.vector_store import ChromaVectorStore
from app.ingestion.preprocessor import DocumentPreprocessor
from app.ingestion.pipeline import IngestionPipeline
from app.connectors.filesystem import FileSystemConnector
from app.eval.harness import EvalHarness

logger = logging.getLogger(__name__)

app = FastAPI(title="Enterprise Knowledge Search", version="1.0.0")

# ── Lazy singletons ──
_backend = None
_store = None
_pipeline = None


def _get_backend():
    global _backend
    if _backend is None:
        _backend = get_backend(get_settings())
    return _backend


def _get_store():
    global _store
    if _store is None:
        s = get_settings()
        _store = ChromaVectorStore(path=s.chroma_path, collection_name=s.chroma_collection)
    return _store


def _get_pipeline():
    global _pipeline
    if _pipeline is None:
        s = get_settings()
        _pipeline = IngestionPipeline(
            backend=_get_backend(),
            store=_get_store(),
            batch_size=s.ingest_batch_size,
            max_retries=s.ingest_max_retries,
        )
    return _pipeline


def reset_singletons():
    """For testing — reset all cached singletons."""
    global _backend, _store, _pipeline
    _backend = None
    _store = None
    _pipeline = None


# ── Routes ──

@app.get("/health")
def health():
    s = get_settings()
    backend = _get_backend()
    store = _get_store()
    return {
        "status": "ok",
        "backend": backend.name,
        "model_id": s.local_model_id if backend.name == "local" else s.jina_model,
        "embed_dim": backend.embed_dim,
        "collection": s.chroma_collection,
        "document_count": store.count(),
        "chroma_path": s.chroma_path,
    }


@app.get("/stats")
def stats():
    store = _get_store()
    return store.stats()


@app.get("/corpus")
def corpus(limit: int = 200):
    store = _get_store()
    documents = store.documents(limit=limit)
    return {
        "total_chunks": store.count(),
        "document_count": len(documents),
        "documents": documents,
    }


@app.post("/ingest")
def ingest(body: dict):
    req = IngestRequest.from_dict(body)

    if req.source == "filesystem":
        try:
            connector = FileSystemConnector(req.path, recursive=req.recursive)
            documents = list(connector.scan())
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e))
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported source: {req.source}")

    result = _get_pipeline().ingest_documents(documents, acl_groups=req.acl_groups)
    return dataclasses.asdict(result)


@app.post("/search")
def search(body: dict):
    req = SearchRequest.from_dict(body)
    if not req.query_text and not req.query_image_b64:
        raise HTTPException(status_code=400, detail="query_text or query_image_b64 required")

    backend = _get_backend()
    store = _get_store()

    t0 = time.monotonic()

    # Build query input
    query_inputs = []
    if req.query_text:
        query_inputs.append(req.query_text)
    if req.query_image_b64:
        import base64
        import io
        try:
            from PIL import Image
            img_bytes = base64.b64decode(req.query_image_b64)
            img = Image.open(io.BytesIO(img_bytes))
            query_inputs.append(img)
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"Invalid image_b64: {e}")

    import numpy as np
    if req.query_text and not req.query_image_b64:
        query_vec = backend.embed_query(req.query_text)
    else:
        # If multiple inputs, embed them all and average
        embeddings = backend.embed(query_inputs)
        query_vec = embeddings.mean(axis=0)
        norm = np.linalg.norm(query_vec)
        if norm > 0:
            query_vec /= norm

    results = store.query(
        query_embedding=query_vec,
        n_results=req.n_results,
        modality_filter=req.modality_filter or None,
        source_filter=req.source_filter or None,
    )

    # Filter by min_score
    results = [r for r in results if r.score >= req.min_score]

    latency_ms = (time.monotonic() - t0) * 1000

    resp = SearchResponse(
        results=results,
        total=len(results),
        query_latency_ms=round(latency_ms, 2),
        backend_used=backend.name,
        embed_dim=backend.embed_dim,
    )
    return dataclasses.asdict(resp)


@app.get("/eval")
def eval_endpoint():
    def search_fn(req: SearchRequest):
        from app.models import SearchResponse
        import dataclasses
        raw = search(dataclasses.asdict(req))
        # Reconstruct SearchResponse from dict
        results = [SearchResult(**r) for r in raw["results"]]
        return SearchResponse(
            results=results,
            total=raw["total"],
            query_latency_ms=raw["query_latency_ms"],
            backend_used=raw["backend_used"],
            embed_dim=raw["embed_dim"],
        )

    golden_path = Path(__file__).parent.parent / "data" / "golden" / "golden_pairs.json"
    harness = EvalHarness(search_fn=search_fn, golden_path=golden_path)
    report = harness.run()
    return dataclasses.asdict(report)


@app.get("/", response_class=HTMLResponse)
def dashboard():
    dashboard_path = Path(__file__).parent.parent / "dashboard" / "index.html"
    if dashboard_path.exists():
        return HTMLResponse(content=dashboard_path.read_text())
    return HTMLResponse(content="<h1>Dashboard not found</h1>", status_code=404)
