from typing import Optional

from pydantic import BaseModel, Field


class RetrieveRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    ticket_text: str = Field(min_length=1)
    top_k: int = Field(default=5, ge=1, le=20)
    tau: float = Field(default=0.01, gt=0)
    weight: float = Field(default=1.5, gt=0)


class RetrieveResult(BaseModel):
    article_id: str
    title: str
    score: float
    snippet: str
    matched_original_terms: list[str] = Field(default_factory=list)
    matched_enriched_terms: list[str] = Field(default_factory=list)


class RetrieveResponse(BaseModel):
    results: list[RetrieveResult]
    sketch_terms_generated: list[str]
    sketch_terms_validated: list[str]
    sketch_terms_rejected: list[str]
    fallback_used: bool
    latency_ms: int
    hallucination_rate: float
    warning: Optional[str] = None


class HealthResponse(BaseModel):
    bm25_index_loaded: bool
    corpus_size: int
    index_built_at: Optional[str] = None


class FeedbackRequest(BaseModel):
    ticket_id: str = Field(min_length=1)
    selected_article_id: str = Field(min_length=1)
    rating: Optional[int] = Field(default=None, ge=1, le=5)
    comments: Optional[str] = None


class FeedbackResponse(BaseModel):
    ok: bool
    message: str
