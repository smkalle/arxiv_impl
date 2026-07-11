"""FastAPI routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

from metaorch import __version__
from metaorch.api.deps import get_executor, get_run_store
from metaorch.api.schemas import (
    ErrorResponse,
    HealthResponse,
    PipelineResponse,
    RunRequest,
    RunsResponse,
    StageDescriptor,
)
from metaorch.contract import CANONICAL_FULL_RUN, PIPELINE_DAG
from metaorch.errors import PlanValidationError
from metaorch.models import StageKind

router = APIRouter()


def _adapter_input_keys(adapter: Any) -> list[str]:
    return _STAGE_INPUT_KEYS.get(type(adapter), [])


_STAGE_INPUT_KEYS: dict[type, list[str]] = {}
_STAGE_OUTPUT_KEYS: dict[type, list[str]] = {}


def _populate_keys() -> None:
    from metaorch.adapters import (
        AaflowAdapter,
        DataMasterAdapter,
        EvolvememAdapter,
        JinaAdapter,
        RgqmAdapter,
        SiraAdapter,
        SiraIngestorAdapter,
        TkmemAdapter,
    )
    _STAGE_INPUT_KEYS.update({
        AaflowAdapter: ["source_path", "source_type", "batch_size", "embed_model"],
        SiraIngestorAdapter: ["kb_articles", "ollama_model", "tau", "weight_w"],
        JinaAdapter: ["query_text", "n_results", "modality_filter", "source_filter", "acl_groups"],
        SiraAdapter: ["ticket_text", "top_k", "tau", "weight_w", "corpus"],
        TkmemAdapter: ["ticket_text", "top_k", "filters", "session_id?"],
        DataMasterAdapter: ["sku_ids", "sources", "min_delta_threshold", "dry_run"],
        EvolvememAdapter: ["start_from", "baseline_f1", "max_rounds", "only?"],
        RgqmAdapter: ["mode", "budget", "checkpoint", "task_set"],
    })
    _STAGE_OUTPUT_KEYS.update({
        AaflowAdapter: ["arrow_path", "faiss_path", "run_summary", "table_schema"],
        SiraIngestorAdapter: ["enriched_kb_path", "kb_index_path", "setup_summary", "enriched_corpus"],
        JinaAdapter: ["results", "total", "query_latency_ms", "backend_used", "embed_dim"],
        SiraAdapter: ["results", "sketch_terms_generated", "sketch_terms_validated",
                      "sketch_terms_rejected", "fallback_used", "latency_ms", "fallback_reason?"],
        TkmemAdapter: ["results", "retrieval_trace"],
        DataMasterAdapter: ["job_id", "status", "skus_processed", "skus_enriched",
                            "skus_rejected", "avg_score_delta", "manifests_committed",
                            "provenance_artifact"],
        EvolvememAdapter: ["loop_results", "final_config_version", "fitness_gain"],
        RgqmAdapter: ["final_archive_summary", "coder_pass_rate", "blended_tokens",
                      "baseline_tokens", "erasure_invariant_holds", "epoch_events"],
    })


_populate_keys()


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    ex = get_executor()
    return HealthResponse(
        status="ok",
        adapters_loaded=len(ex.adapters),
        stages_available=[s.value for s in StageKind],
        version=__version__,
    )


@router.get("/pipelines", response_model=PipelineResponse)
def pipelines() -> PipelineResponse:
    return PipelineResponse(
        name="canonical-full-run",
        stages=[s.value for s in CANONICAL_FULL_RUN],
        dag={k.value: [d.value for d in deps] for k, deps in PIPELINE_DAG.items()},
    )


@router.get("/stages", response_model=list[StageDescriptor])
def list_stages() -> list[StageDescriptor]:
    ex = get_executor()
    out: list[StageDescriptor] = []
    for kind in StageKind:
        adapter = ex.adapters[kind]
        out.append(
            StageDescriptor(
                kind=kind.value,
                adapter_name=adapter.name,
                adapter_version=adapter.version,
                input_keys=_STAGE_INPUT_KEYS.get(type(adapter), []),
                output_keys=_STAGE_OUTPUT_KEYS.get(type(adapter), []),
            )
        )
    return out


@router.post("/runs", response_model=RunsResponse,
             responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}})
def create_run(req: RunRequest) -> RunsResponse:
    plan, context = req.with_defaults()
    ex = get_executor()
    try:
        run = ex.execute(plan, context)
    except PlanValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))
    get_run_store().put(run)
    return RunsResponse(run=run)


@router.get("/runs/{run_id}", response_model=RunsResponse,
             responses={404: {"model": ErrorResponse}})
def get_run(run_id: str) -> RunsResponse:
    run = get_run_store().get(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail=f"run {run_id} not found")
    return RunsResponse(run=run)