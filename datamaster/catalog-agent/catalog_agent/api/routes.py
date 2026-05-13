import asyncio
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse

from catalog_agent.api.models import (
    EnrichRequest, EnrichResponse, JobStatus,
    RollbackRequest, RollbackResponse,
)
from catalog_agent.pool.models import ManifestMeta

router = APIRouter()

# In-process job registry (suitable for single-worker dev/test; replace with ARQ for prod)
_job_registry: dict[str, JobStatus] = {}
_job_tasks: dict[str, asyncio.Task] = {}


def get_app_state(request):
    return request.app.state


@router.post("/enrich", response_model=EnrichResponse, status_code=202)
async def enrich(body: EnrichRequest, request=None):
    from fastapi import Request
    job_id = uuid.uuid4().hex[:12]
    state = request.app.state

    initial_status = JobStatus(job_id=job_id, status="queued")
    _job_registry[job_id] = initial_status

    async def _run():
        _job_registry[job_id] = JobStatus(job_id=job_id, status="running")
        try:
            from catalog_agent.agent.loop import run_enrichment_job
            result = await run_enrichment_job(
                job_id=job_id,
                request=body,
                pool=state.pool,
                memory=state.memory,
                scorer=state.scorer,
                sku_store=state.sku_store,
                sources=state.sources,
                writer=state.writer,
                settings=state.settings,
            )
            _job_registry[job_id] = result
        except Exception as e:
            _job_registry[job_id] = JobStatus(job_id=job_id, status="failed", error=str(e))

    task = asyncio.create_task(_run())
    _job_tasks[job_id] = task

    sku_count = len(body.sku_ids) if body.sku_ids else 50
    return EnrichResponse(
        job_id=job_id,
        estimated_skus=sku_count,
        eta_seconds=max(5, sku_count * 2),
    )


@router.get("/job/{job_id}", response_model=JobStatus)
async def get_job(job_id: str):
    status = _job_registry.get(job_id)
    if status is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return status


@router.get("/jobs", response_model=list[JobStatus])
async def list_jobs():
    return list(_job_registry.values())


@router.get("/pool", response_model=list[ManifestMeta])
async def get_pool(
    request=None,
    category: str | None = Query(None),
    source: str | None = Query(None),
    min_delta: float | None = Query(None),
    committed: bool | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    state = request.app.state
    manifests = await state.pool.get_candidates(
        committed=committed,
        min_delta=min_delta,
    )
    if source:
        manifests = [m for m in manifests if m.meta.source == source]
    start = (page - 1) * page_size
    return [m.meta for m in manifests[start:start + page_size]]


@router.post("/rollback", response_model=RollbackResponse)
async def rollback(body: RollbackRequest, request=None):
    state = request.app.state
    snapshot = await state.sku_store.get_rollback_snapshot(body.sku_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="No rollback snapshot found")
    original_attrs = snapshot.get("attributes", {})
    await state.sku_store.update(body.sku_id, original_attrs)

    manifest = await state.pool.get(body.manifest_id)
    if manifest:
        manifest.meta.committed = False
        await state.pool.add(manifest)

    return RollbackResponse(rolled_back=True, sku_id=body.sku_id)


@router.get("/health")
async def health(request=None):
    state = request.app.state
    if state.settings.use_fake_redis:
        redis_ok = "fake"
    else:
        redis_ok = "ok"
        try:
            await state.pool._redis.ping()
        except Exception:
            redis_ok = "error"
    return {
        "status": "ok",
        "redis": redis_ok,
        "cataloglab": "mock" if state.settings.use_mock_scorer else "ok",
        "sku_store": "mock" if state.settings.use_mock_sku_store else "ok",
    }


@router.get("/memory/{category}", response_model=dict)
async def get_memory(category: str, request=None):
    state = request.app.state
    top_sources = await state.memory.get_top_sources(category)
    fill_rates = await state.memory.get_fill_rates(category)
    recent = await state.memory.get_recent_outcomes(category, limit=20)
    return {
        "category": category,
        "top_sources": top_sources,
        "fill_rates": fill_rates,
        "recent_outcomes": recent,
    }
