"""Pipeline executor: topological DAG execution with contract validation and provenance."""

from __future__ import annotations

import hashlib
import json
import uuid
from typing import Any

from metaorch.contract import Adapter, PIPELINE_DAG, CANONICAL_FULL_RUN
from metaorch.errors import (
    AdapterError,
    ContractError,
    CyclicDag,
    MissingAdapter,
    PlanValidationError,
)
from metaorch.models import (
    PipelineContext,
    PipelineRun,
    Provenance,
    RunPlan,
    StageKind,
    StageResult,
    utcnow,
)


def _hash_summary(value: Any) -> str:
    try:
        s = json.dumps(value, sort_keys=True, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        s = repr(value)
    return "sha1:" + hashlib.sha1(s.encode("utf-8", errors="replace")).hexdigest()[:16]


def _summarize(value: Any) -> dict[str, Any]:
    """Reduce a payload to counts/hashes — never the raw payload."""
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(v, list):
                out[k] = {"count": len(v), "hash": _hash_summary(v[:50])}
            elif isinstance(v, dict):
                out[k] = {
                    "keys": list(v.keys())[:10],
                    "hash": _hash_summary(v),
                }
            elif isinstance(v, (int, float, bool, str)) or v is None:
                out[k] = {"value": v, "type": type(v).__name__}
            else:
                out[k] = {"type": type(v).__name__, "hash": _hash_summary(v)}
        return out
    if isinstance(value, list):
        return {"count": len(value), "hash": _hash_summary(value[:50])}
    return {"type": type(value).__name__, "hash": _hash_summary(value)}


def topo_order(stages: list[StageKind]) -> list[StageKind]:
    """Return stages in a valid topological order w.r.t. PIPELINE_DAG. Reject cycles + unknown stages."""
    declared = set(stages)
    for s in stages:
        if s not in PIPELINE_DAG:
            raise PlanValidationError(f"unknown stage {s}")
        # all hard deps must be in the plan
        for dep in PIPELINE_DAG[s]:
            if dep not in declared:
                raise PlanValidationError(f"stage {s} requires dependency {dep} which is not in the plan")
    visited: dict[StageKind, int] = {}  # 0 = visiting, 1 = done
    out: list[StageKind] = []

    def visit(n: StageKind, path: list[StageKind]) -> None:
        if visited.get(n) == 1:
            return
        if visited.get(n) == 0:
            raise CyclicDag(f"cycle through {n} via {path}")
        visited[n] = 0
        for dep in PIPELINE_DAG[n]:
            if dep in declared:
                visit(dep, path + [n])
        visited[n] = 1
        out.append(n)

    for s in stages:
        visit(s, [])
    # `out` is in topo order respecting deps; preserve relative order from `stages`.
    return [s for s in out if s in declared]


def _strictly_precedes(a: StageKind, b: StageKind) -> bool:
    """True if stage `a` is a transitive hard dependency of `b` in PIPELINE_DAG."""
    seen: set[StageKind] = set()
    stack = [b]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        for dep in PIPELINE_DAG[n]:
            if dep == a:
                return True
            stack.append(dep)
    return False


class PipelineExecutor:
    """Execute a RunPlan against a registered set of adapters."""

    def __init__(self, adapters: dict[StageKind, Adapter] | None = None) -> None:
        if adapters is None:
            from metaorch.adapters import default_adapters

            adapters = default_adapters()
        missing = [s for s in StageKind if s not in adapters]
        if missing:
            raise MissingAdapter(f"adapters not registered for: {missing}")
        self.adapters = adapters

    def execute(self, plan: RunPlan, context: PipelineContext) -> PipelineRun:
        run_id = uuid.uuid4().hex
        started_at = utcnow()

        if plan.resume_from is not None and plan.resume_from not in plan.stages:
            raise PlanValidationError(
                f"resume_from stage {plan.resume_from} is not in the plan's stages {plan.stages}"
            )

        ordered = topo_order(plan.stages)

        results: list[StageResult] = []
        artifacts_by_stage: dict[StageKind, dict[str, Any]] = {}
        halted: str | None = None  # error reason for the first failed stage, or None

        for stage in ordered:
            if plan.resume_from is not None and _strictly_precedes(stage, plan.resume_from):
                prov = Provenance(
                    stage=stage,
                    adapter=self.adapters[stage].name,
                    adapter_version=self.adapters[stage].version,
                    started_at=started_at,
                    finished_at=started_at,
                    duration_ms=0,
                    config={},
                    inputs_summary={"note": "skipped via resume_from"},
                    outputs_summary={},
                    status="skipped",
                    error=None,
                )
                results.append(StageResult(stage=stage, provenance=prov, artifacts={}))
                continue

            inputs = self._gather_inputs(stage, context, artifacts_by_stage)
            config = plan.config_for(stage)
            # Config overrides ride on top of default inputs so stage_configs actually take effect.
            # Only override keys already in inputs — never inject new keys (would risk validate_inputs failures).
            for k, v in config.items():
                if k in inputs:
                    inputs[k] = v
            adapter = self.adapters[stage]
            t0 = utcnow()

            status_ok = True
            outputs: dict[str, Any] = {}
            err: str | None = None
            try:
                adapter.validate_inputs(inputs)
                outputs = adapter.run(inputs, config)
                adapter.validate_outputs(outputs)
            except (ContractError, AdapterError) as e:
                status_ok = False
                err = str(e)

            t1 = utcnow()
            stage_status = "ok" if status_ok else "failed"
            prov = Provenance(
                stage=stage,
                adapter=adapter.name,
                adapter_version=adapter.version,
                started_at=t0,
                finished_at=t1,
                duration_ms=int((t1 - t0).total_seconds() * 1000),
                config=config,
                inputs_summary=_summarize({k: v for k, v in inputs.items() if k != "corpus"}),
                outputs_summary=_summarize(outputs) if status_ok else {},
                status=stage_status,
                error=err,
            )
            results.append(StageResult(stage=stage, provenance=prov, artifacts=outputs))
            if not status_ok:
                if halted is None:
                    halted = err or "stage failed"
                break
            artifacts_by_stage[stage] = outputs

        finished_at = utcnow()
        return PipelineRun(
            run_id=run_id,
            plan=plan,
            started_at=started_at,
            finished_at=finished_at,
            status="failed" if halted is not None else "completed",
            stage_results=results,
        )

    def _gather_inputs(
        self,
        stage: StageKind,
        context: PipelineContext,
        artifacts: dict[StageKind, dict[str, Any]],
    ) -> dict[str, Any]:
        ingest = artifacts.get(StageKind.INGEST, {})
        kb_enrich = artifacts.get(StageKind.KB_ENRICH, {})
        retrieve = artifacts.get(StageKind.RETRIEVE, {})
        ticketmind = artifacts.get(StageKind.TICKETMIND, {})
        mm = artifacts.get(StageKind.MM_SEARCH, {})
        catalog = artifacts.get(StageKind.CATALOG, {})

        if stage == StageKind.INGEST:
            return {
                "source_path": context.extras.get("source_path", "fixtures/zendesk_1k.csv"),
                "source_type": context.extras.get("source_type", "zendesk"),
                "batch_size": 128,
                "embed_model": "all-MiniLM-L6-v2",
            }
        if stage == StageKind.KB_ENRICH:
            return {
                "kb_articles": context.kb_articles,
                "ollama_model": "qwen2.5:3b",
                "tau": 0.01,
                "weight_w": 1.5,
            }
        if stage == StageKind.MM_SEARCH:
            return {
                "query_text": context.ticket_text or "how do I reset my MFA?",
                "n_results": 4,
                "modality_filter": [],
                "source_filter": [],
                "acl_groups": context.acl_groups,
            }
        if stage == StageKind.CATALOG:
            return {
                "sku_ids": context.sku_ids or ["RAK-TEST-001"],
                "sources": context.sources or ["gs1", "open_food_facts"],
                "min_delta_threshold": 2.0,
                "dry_run": False,
            }
        if stage == StageKind.RETRIEVE:
            corpus = kb_enrich.get("enriched_corpus", [])
            return {
                "ticket_text": context.ticket_text or "how do I reset my MFA?",
                "top_k": 5,
                "tau": 0.01,
                "weight_w": 1.5,
                "corpus": corpus,
            }
        if stage == StageKind.TICKETMIND:
            corpus = kb_enrich.get("enriched_corpus", [])
            return {
                "ticket_text": context.ticket_text or "how do I reset my MFA?",
                "top_k": 5,
                "filters": {"product_area": None, "date_from": None},
                "session_id": context.extras.get("session_id"),
            }
        if stage == StageKind.EVOLVE:
            # EVOLVE ingests retrieval artifacts as evidence (the soft CATALOG feed
            # is recorded as inputs_summary when present).
            evidence = {
                "retrieved_articles": retrieve.get("results", []),
                "ticketmind_results": ticketmind.get("results", []),
                "mm_search_results": mm.get("results", []),
                "catalog_manifests": catalog.get("manifests_committed", 0),
            }
            return {
                "start_from": "L1",
                "baseline_f1": 0.34,
                "max_rounds": 7,
                "evidence": evidence,
            }
        if stage == StageKind.COEVOLVE:
            evolved = artifacts.get(StageKind.EVOLVE, {}).get("final_config_version", "baseline")
            return {
                "mode": "rqgm",
                "budget": 80,
                "checkpoint": 30,
                "task_set": "tasks/humaneval_20.json",
                "evolved_config_version": evolved,
            }
        raise PlanValidationError(f"no input mapping for stage {stage}")


__all__ = ["PipelineExecutor", "topo_order", "canonical_full_run_plan"]


def canonical_full_run_plan() -> RunPlan:
    return RunPlan(stages=list(CANONICAL_FULL_RUN))