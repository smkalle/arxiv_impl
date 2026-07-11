"""HTTP request/response schemas."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from metaorch.models import PipelineContext, PipelineRun, RunPlan


class RunRequest(BaseModel):
    plan: RunPlan = Field(default_factory=lambda: RunPlan(stages=[]))
    context: PipelineContext = Field(default_factory=PipelineContext)

    def with_defaults(self) -> tuple[RunPlan, PipelineContext]:
        from metaorch.pipeline import canonical_full_run_plan, default_context

        plan = self.plan if self.plan.stages else canonical_full_run_plan()
        # Merge: start from defaults, overlay any user-supplied non-empty fields.
        # This keeps a bare POST /runs working AND lets a user override just `ticket_text`
        # without dropping the default `kb_articles`/`sku_ids` (which would otherwise fail
        # KB_ENRICH / CATALOG contract validation).
        base = default_context()
        user = self.context
        merged = base.model_copy(update={
            "ticket_text": user.ticket_text or base.ticket_text,
            "kb_articles": user.kb_articles or base.kb_articles,
            "sku_ids": user.sku_ids or base.sku_ids,
            "sources": user.sources or base.sources,
            "acl_groups": user.acl_groups or base.acl_groups,
            "extras": {**base.extras, **user.extras},
        })
        return plan, merged


class RunsResponse(BaseModel):
    run: PipelineRun


class HealthResponse(BaseModel):
    status: str
    adapters_loaded: int
    stages_available: list[str]
    version: str


class PipelineResponse(BaseModel):
    name: str
    stages: list[str]
    dag: dict[str, list[str]]


class StageDescriptor(BaseModel):
    kind: str
    adapter_name: str
    adapter_version: str
    input_keys: list[str]
    output_keys: list[str]


class ErrorResponse(BaseModel):
    error: str
    detail: Any = None