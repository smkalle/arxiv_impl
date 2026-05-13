"""
Pydantic request/response models for kb-ingestor admin dashboard API.
"""
from __future__ import annotations

from typing import Any, List, Optional
from pydantic import BaseModel, Field


# ── Auth ────────────────────────────────────────────────────────────────────

class TokenRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    role: str
    username: str


# ── Runs ────────────────────────────────────────────────────────────────────

class TriggerRunRequest(BaseModel):
    source_filename: str
    source_type: str = "zendesk"      # zendesk | jira
    index_name: str = "support-kb"
    batch_size: int = Field(128, ge=16, le=512)
    max_workers: int = Field(4, ge=1, le=16)
    embed_model: str = "all-MiniLM-L6-v2"
    max_chunk_chars: int = Field(512, ge=64, le=2048)
    null_policy: str = "drop"         # drop | raise
    append_mode: bool = False
    config_id: Optional[str] = None


class BatchOut(BaseModel):
    batch_id: str
    run_id: str
    batch_index: int
    rows: int
    status: str
    embed_duration_ms: Optional[int] = None
    error_class: Optional[str] = None
    error_message: Optional[str] = None
    affected_row_ids: Optional[Any] = None
    started_at: Optional[str] = None
    completed_at: Optional[str] = None


class RunOut(BaseModel):
    run_id: str
    source_filename: str
    source_type: str
    index_name: str
    status: str
    triggered_by: str
    trigger_type: str
    rows_total: Optional[int] = None
    rows_ingested: Optional[int] = None
    rows_failed: Optional[int] = None
    batch_size: int
    max_workers: int
    embed_model: str
    max_chunk_chars: int
    null_policy: str
    append_mode: int
    t_load_ms: Optional[int] = None
    t_preprocess_ms: Optional[int] = None
    t_embed_ms: Optional[int] = None
    t_upsert_ms: Optional[int] = None
    t_total_ms: Optional[int] = None
    baseline_t_ms: Optional[int] = None
    speedup_x: Optional[float] = None
    success_rate: Optional[float] = None
    error_summary: Optional[Any] = None
    queued_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    batches: Optional[List[BatchOut]] = None


class RunsPage(BaseModel):
    items: List[RunOut]
    total: int
    page: int
    limit: int


class RetryRequest(BaseModel):
    batch_ids: List[str]


class ValidateRequest(BaseModel):
    source_filename: str
    source_type: Optional[str] = None


class ValidateResponse(BaseModel):
    valid: bool
    detected_source_type: str
    row_count: int
    columns_found: List[str]
    columns_missing: List[str]
    null_counts: dict
    message: str


class EstimateRequest(BaseModel):
    row_count: int
    batch_size: int = 128
    embed_model: str = "all-MiniLM-L6-v2"


class EstimateResponse(BaseModel):
    estimated_seconds: float
    p50_throughput: float
    estimated_batches: int


# ── Indexes ─────────────────────────────────────────────────────────────────

class IndexOut(BaseModel):
    index_name: str
    doc_count: int
    embed_dim: int
    embed_model: str
    last_updated: str
    size_bytes_arrow: Optional[int] = None
    size_bytes_faiss: Optional[int] = None
    artifact_dir: str
    consistency_status: str
    consistency_checked_at: Optional[str] = None
    soft_deleted: int
    runs: Optional[List[RunOut]] = None


class IndexesPage(BaseModel):
    items: List[IndexOut]
    total: int


# ── Configs ─────────────────────────────────────────────────────────────────

class ConfigIn(BaseModel):
    config_name: str
    source_type: Optional[str] = None
    batch_size: int = 128
    max_workers: int = 4
    max_chunk_chars: int = 512
    min_chunk_chars: int = 20
    null_policy: str = "drop"
    faiss_factory: str = "Flat"
    embed_model: str = "all-MiniLM-L6-v2"


class ConfigOut(ConfigIn):
    config_id: str
    created_by: str
    created_at: str
    updated_at: Optional[str] = None


# ── Audit log ────────────────────────────────────────────────────────────────

class AuditEntry(BaseModel):
    log_id: int
    username: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    detail: Optional[Any] = None
    ip_address: Optional[str] = None
    recorded_at: str


class AuditPage(BaseModel):
    items: List[AuditEntry]
    total: int
    page: int
    limit: int
