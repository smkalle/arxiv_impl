from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class IngestAndRetrieveConfig:
    batch_size: int = 128
    max_workers: int = 4
    embed_model: str = "deterministic-hash"
    max_chunk_chars: int = 512
    min_chunk_chars: int = 20

    enrichment_model: str = "qwen2.5-coder:3b"
    enrichment_temperature: float = 0.3
    enrichment_terms_per_article: int = 10
    ollama_host: str = "http://127.0.0.1:11435"
    enrichment_timeout_s: int = 300

    tau: float = 0.01
    weight: float = 1.5
    top_k: int = 5

    output_path: Path | None = None
    append_mode: bool = False


@dataclass(slots=True)
class IngestAndRetrieveResult:
    ticket_result: Any | None = None
    kb_summary: dict[str, Any] = field(default_factory=dict)
    combined_metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, str] = field(default_factory=dict)
