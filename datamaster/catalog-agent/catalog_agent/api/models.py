from pydantic import BaseModel
from typing import Literal, Any


class EnrichRequest(BaseModel):
    sku_ids: list[str] | None = None
    quality_filter: dict[str, Any] | None = None   # e.g. {"max_score": 65}
    categories: list[str] | None = None
    sources: list[str] | None = None
    min_delta_threshold: float = 2.0
    dry_run: bool = False


class EnrichResponse(BaseModel):
    job_id: str
    estimated_skus: int
    eta_seconds: int


class JobStatus(BaseModel):
    job_id: str
    status: Literal["queued", "running", "completed", "failed"]
    skus_processed: int = 0
    skus_enriched: int = 0
    skus_rejected: int = 0
    avg_score_delta: float | None = None
    manifests_committed: int = 0
    provenance_artifact: str | None = None
    enriched_at: str | None = None
    error: str | None = None


class RollbackRequest(BaseModel):
    manifest_id: str
    sku_id: str


class RollbackResponse(BaseModel):
    rolled_back: bool
    sku_id: str


class PoolQueryParams(BaseModel):
    category: str | None = None
    source: str | None = None
    min_delta: float | None = None
    committed: bool | None = None
    page: int = 1
    page_size: int = 50
