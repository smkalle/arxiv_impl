"""Shared data models for the Enterprise Knowledge Search system."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
import hashlib
import json


@dataclass
class Document:
    """Output of a connector — one logical source asset."""
    id: str                                # "src:{system}:{path_or_id}"
    content: Any                           # str | PIL.Image | Path
    modality: str                          # text | image | audio | video | pdf
    source_system: str                     # filesystem | confluence | notion | figma | loom
    asset_url: str                         # original path or URL
    metadata: dict = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    content_hash: str = ""                 # SHA256 — set by connector or preprocessor

    def __post_init__(self):
        if not self.content_hash:
            self.content_hash = self._compute_hash()

    def _compute_hash(self) -> str:
        if isinstance(self.content, str):
            raw = self.content.encode()
        elif isinstance(self.content, bytes):
            raw = self.content
        else:
            raw = str(self.content).encode()
        return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]


@dataclass
class Chunk:
    """A single embeddable unit produced by the preprocessor."""
    id: str                                # "{doc_id}:chunk_{n}"
    document_id: str
    content: Any                           # str | PIL.Image | Path
    modality: str
    source_system: str
    asset_url: str
    chunk_index: int = 0
    token_count: int = 0
    acl_groups: list[str] = field(default_factory=lambda: ["public"])
    metadata: dict = field(default_factory=dict)
    content_hash: str = ""
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def __post_init__(self):
        if not self.content_hash:
            if isinstance(self.content, str):
                raw = (self.document_id + str(self.chunk_index) + self.content).encode()
            else:
                raw = (self.document_id + str(self.chunk_index)).encode()
            self.content_hash = "sha256:" + hashlib.sha256(raw).hexdigest()[:16]

    def metadata_for_chroma(self) -> dict:
        """Flatten to Chroma-compatible flat dict (string/int/float values only)."""
        return {
            "modality": self.modality,
            "source_system": self.source_system,
            "asset_url": self.asset_url,
            "chunk_index": self.chunk_index,
            "token_count": self.token_count,
            "acl_groups": json.dumps(self.acl_groups),
            "content_hash": self.content_hash,
            "document_id": self.document_id,
            "created_at": self.created_at.isoformat(),
            **{k: str(v) if not isinstance(v, (str, int, float, bool)) else v
               for k, v in self.metadata.items()},
        }

    def text_for_chroma(self) -> str:
        """Text to store in Chroma's document field."""
        if isinstance(self.content, str):
            return self.content
        return f"[{self.modality}:{self.asset_url}]"


# ── API models (plain dataclasses, also usable as Pydantic) ──

@dataclass
class IngestRequest:
    source: str = "filesystem"
    path: str = "./data/samples"
    acl_groups: list[str] = field(default_factory=lambda: ["public"])
    recursive: bool = True

    @classmethod
    def from_dict(cls, d: dict) -> "IngestRequest":
        return cls(
            source=d.get("source", "filesystem"),
            path=d.get("path", "./data/samples"),
            acl_groups=d.get("acl_groups", ["public"]),
            recursive=d.get("recursive", True),
        )


@dataclass
class IngestResponse:
    status: str
    ingested: int
    skipped: int
    failed: int
    duration_ms: float
    errors: list[str] = field(default_factory=list)


@dataclass
class SearchRequest:
    query_text: str | None = None
    query_image_b64: str | None = None
    n_results: int = 10
    modality_filter: list[str] = field(default_factory=list)
    source_filter: list[str] = field(default_factory=list)
    min_score: float = 0.0

    @classmethod
    def from_dict(cls, d: dict) -> "SearchRequest":
        return cls(
            query_text=d.get("query_text"),
            query_image_b64=d.get("query_image_b64"),
            n_results=d.get("n_results", 10),
            modality_filter=d.get("modality_filter", []),
            source_filter=d.get("source_filter", []),
            min_score=d.get("min_score", 0.0),
        )


@dataclass
class SearchResult:
    id: str
    score: float
    modality: str
    source_system: str
    snippet: str
    asset_url: str
    chunk_index: int
    metadata: dict = field(default_factory=dict)


@dataclass
class SearchResponse:
    results: list[SearchResult]
    total: int
    query_latency_ms: float
    backend_used: str
    embed_dim: int


@dataclass
class EvalPair:
    id: str
    query_text: str
    expected_doc_ids: list[str]       # document-level ids (prefix match on chunk ids)
    modality: str = "text"


@dataclass
class EvalReport:
    precision_at_1: float
    precision_at_3: float
    precision_at_5: float
    recall_at_5: float
    mrr: float
    latency_p50_ms: float
    latency_p95_ms: float
    total_queries: int
    details: list[dict] = field(default_factory=list)
