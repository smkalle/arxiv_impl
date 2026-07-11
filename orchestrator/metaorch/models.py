"""Pydantic models for the metaorch pipeline."""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


class StageKind(str, Enum):
    INGEST = "INGEST"
    KB_ENRICH = "KB_ENRICH"
    MM_SEARCH = "MM_SEARCH"
    CATALOG = "CATALOG"
    RETRIEVE = "RETRIEVE"
    TICKETMIND = "TICKETMIND"
    EVOLVE = "EVOLVE"
    COEVOLVE = "COEVOLVE"


StageStatus = Literal["ok", "skipped", "failed"]
RunStatus = Literal["queued", "running", "completed", "failed"]


class Provenance(BaseModel):
    stage: StageKind
    adapter: str
    adapter_version: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    config: dict[str, Any] = Field(default_factory=dict)
    inputs_summary: dict[str, Any] = Field(default_factory=dict)
    outputs_summary: dict[str, Any] = Field(default_factory=dict)
    status: StageStatus
    error: str | None = None


class StageResult(BaseModel):
    stage: StageKind
    provenance: Provenance
    artifacts: dict[str, Any] = Field(default_factory=dict)


class StageConfig(BaseModel):
    """Per-stage config overrides applied by the executor to the adapter call."""

    config: dict[str, Any] = Field(default_factory=dict)


class RunPlan(BaseModel):
    stages: list[StageKind]
    stage_configs: dict[StageKind, dict[str, Any]] = Field(default_factory=dict)
    resume_from: StageKind | None = None

    def config_for(self, stage: StageKind) -> dict[str, Any]:
        return self.stage_configs.get(stage, {})


class PipelineContext(BaseModel):
    """User-supplied inputs that feed stage roots (ticket_text, kb_articles, skus, ...)."""

    ticket_text: str | None = None
    kb_articles: list[dict[str, Any]] = Field(default_factory=list)
    sku_ids: list[str] = Field(default_factory=list)
    sources: list[str] = Field(default_factory=list)
    acl_groups: list[str] = Field(default_factory=list)
    extras: dict[str, Any] = Field(default_factory=dict)


class PipelineRun(BaseModel):
    run_id: str
    plan: RunPlan
    started_at: datetime
    finished_at: datetime | None = None
    status: RunStatus
    stage_results: list[StageResult] = Field(default_factory=list)


def utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)