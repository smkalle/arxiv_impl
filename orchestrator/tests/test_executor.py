"""Executor-layer tests: topo order, resume_from, contract failure halts, full run, provenance."""

from __future__ import annotations

from typing import Any

import pytest

from metaorch.adapters import default_adapters
from metaorch.errors import ContractError, PlanValidationError
from metaorch.executor import PipelineExecutor, topo_order
from metaorch.models import PipelineContext, RunPlan, StageKind
from metaorch.pipeline import canonical_full_run_plan, default_context


def test_topo_order_respects_dependencies() -> None:
    from metaorch.contract import CANONICAL_FULL_RUN

    order = topo_order(list(CANONICAL_FULL_RUN))
    # COEVOLVE depends on EVOLVE -> RETRIEVE/TICKETMIND/MM_SEARCH -> INGEST/KB_ENRICH.
    pos = {s: i for i, s in enumerate(order)}
    assert pos[StageKind.INGEST] < pos[StageKind.RETRIEVE]
    assert pos[StageKind.KB_ENRICH] < pos[StageKind.RETRIEVE]
    assert pos[StageKind.RETRIEVE] < pos[StageKind.EVOLVE]
    assert pos[StageKind.MM_SEARCH] < pos[StageKind.EVOLVE]
    assert pos[StageKind.EVOLVE] < pos[StageKind.COEVOLVE]


def test_topo_order_rejects_missing_hard_dep() -> None:
    with pytest.raises(PlanValidationError, match="requires dependency"):
        topo_order([StageKind.RETRIEVE])  # needs INGEST + KB_ENRICH


def test_full_pipeline_end_to_end_via_executor(default_context: PipelineContext) -> None:
    run = PipelineExecutor().execute(canonical_full_run_plan(), default_context)
    assert run.status == "completed", [(r.stage.value, r.provenance.status, r.provenance.error) for r in run.stage_results]
    statuses = [r.provenance.status for r in run.stage_results]
    assert all(s == "ok" for s in statuses), statuses
    assert {r.stage for r in run.stage_results} == set(canonical_full_run_plan().stages)


def test_provenance_recorded_for_every_stage(default_context: PipelineContext) -> None:
    run = PipelineExecutor().execute(canonical_full_run_plan(), default_context)
    for r in run.stage_results:
        p = r.provenance
        assert p.adapter and p.adapter_version
        assert p.duration_ms >= 0
        assert p.status == "ok"
        # outputs_summary is squashed to counts/hashes — never raw payloads.
        for v in p.outputs_summary.values():
            assert "value" not in v or isinstance(v.get("value"), (int, float, str, bool)) or v["value"] is None
        # input summaries must not contain raw corpus payloads.
        flat = str(p.inputs_summary)
        assert "enriched_body" not in flat
        assert "snippet" not in flat


def test_resume_from_skips_upstream_stages_only(default_context: PipelineContext) -> None:
    plan = RunPlan(stages=list(canonical_full_run_plan().stages), resume_from=StageKind.EVOLVE)
    run = PipelineExecutor().execute(plan, default_context)
    assert run.status == "completed"
    by_stage = {r.stage: r for r in run.stage_results}
    skipped = [s for s, r in by_stage.items() if r.provenance.status == "skipped"]
    executed = [s for s, r in by_stage.items() if r.provenance.status == "ok"]
    # EVOLVE's hard deps + their transitive deps are skipped.
    for s in (StageKind.INGEST, StageKind.KB_ENRICH, StageKind.RETRIEVE,
              StageKind.TICKETMIND, StageKind.MM_SEARCH):
        assert s in skipped, f"{s} should be skipped"
    # CATALOG is NOT a transitive hard dep; it executes.
    assert StageKind.CATALOG in executed
    # EVOLVE itself + COEVOLVE execute.
    assert StageKind.EVOLVE in executed
    assert StageKind.COEVOLVE in executed


def test_contract_failure_halts_full_run_and_omits_downstream(default_context: PipelineContext) -> None:
    class _BrokenSira:
        kind = StageKind.RETRIEVE
        name = "broken-sira"
        version = "0.0.0"

        def validate_inputs(self, inputs: dict[str, Any]) -> None: pass

        def validate_outputs(self, outputs: dict[str, Any]) -> None:
            raise ContractError("intentionally broken")

        def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
            return {"results": []}

    adapters = default_adapters()
    adapters[StageKind.RETRIEVE] = _BrokenSira()  # type: ignore[assignment]
    run = PipelineExecutor(adapters).execute(canonical_full_run_plan(), default_context)
    assert run.status == "failed"
    stages_present = {r.stage for r in run.stage_results}
    assert StageKind.EVOLVE not in stages_present  # executor halted before running downstream
    assert StageKind.COEVOLVE not in stages_present
    failed = next(r for r in run.stage_results if r.provenance.status == "failed")
    assert failed.stage == StageKind.RETRIEVE
    assert "intentionally broken" in (failed.provenance.error or "")


def test_partial_run_only_specific_stages(default_context: PipelineContext) -> None:
    plan = RunPlan(
        stages=[StageKind.INGEST, StageKind.KB_ENRICH, StageKind.RETRIEVE],
    )
    run = PipelineExecutor().execute(plan, default_context)
    assert run.status == "completed"
    assert {r.stage for r in run.stage_results} == {
        StageKind.INGEST, StageKind.KB_ENRICH, StageKind.RETRIEVE
    }


def test_per_stage_config_applied(default_context: PipelineContext) -> None:
    plan = canonical_full_run_plan()
    plan.stage_configs[StageKind.RETRIEVE] = {"top_k": 2}
    run = PipelineExecutor().execute(plan, default_context)
    retrieve = next(r for r in run.stage_results if r.stage == StageKind.RETRIEVE)
    # The SiraAdapter returns up to top_k results; if config top_k=2 had no effect
    # (settings goes through validate), we still assert <=2 results.
    assert len(retrieve.artifacts["results"]) <= 2