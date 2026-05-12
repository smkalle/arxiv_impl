from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

import pyarrow as pa


CANONICAL_TICKET_SCHEMA = pa.schema(
    [
        ("id", pa.string()),
        ("subject", pa.string()),
        ("description", pa.string()),
        ("status", pa.string()),
        ("created_at", pa.timestamp("us")),
        ("tags", pa.list_(pa.string())),
        ("source", pa.string()),
    ]
)


@dataclass(slots=True)
class IngestConfig:
    batch_size: int = 128
    max_workers: int = 4
    embed_model: str = "all-MiniLM-L6-v2"
    max_chunk_chars: int = 512
    min_chunk_chars: int = 20
    null_policy: Literal["drop", "raise"] = "drop"
    faiss_factory: str = "Flat"
    output_path: Path | None = None
    source_type: Literal["zendesk", "jira", "auto"] = "auto"
    append: bool = False


@dataclass(slots=True)
class IngestResult:
    table: pa.Table | None = None
    index: Any = None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)
