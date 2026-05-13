from __future__ import annotations

import csv
import json
import math
import struct
import time
from dataclasses import dataclass, field
from hashlib import blake2b
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa
import pyarrow.ipc as ipc

from sira_kb_ingestor.models import IngestAndRetrieveConfig


EMBED_DIM = 128


@dataclass
class DeterministicIngestResult:
    table: pa.Table | None = None
    index: Any = None
    metrics: dict[str, Any] = field(default_factory=dict)
    artifacts: dict[str, Any] = field(default_factory=dict)


def _tokenize(text: str) -> list[str]:
    normalized = []
    current = []
    for char in text.lower():
        if char.isalnum():
            current.append(char)
        elif current:
            normalized.append("".join(current))
            current = []
    if current:
        normalized.append("".join(current))
    return normalized


def _hash_embedding(text: str, dim: int = EMBED_DIM) -> list[float]:
    vector = np.zeros(dim, dtype=np.float32)
    for token in _tokenize(text):
        digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
        bucket_raw, sign_raw = struct.unpack(">II", digest)
        bucket = bucket_raw % dim
        sign = 1.0 if sign_raw % 2 == 0 else -1.0
        vector[bucket] += sign
    norm = float(np.linalg.norm(vector))
    if norm > 0:
        vector = vector / norm
    return vector.astype(np.float32).tolist()


def _timestamp_or_none(value: Any) -> Any:
    if not value:
        return None
    return value


def _load_zendesk_csv(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        rows = list(csv.DictReader(fh))
    required = {"id", "subject", "description"}
    if not required.issubset(rows[0].keys() if rows else set()):
        missing = sorted(required - set(rows[0].keys() if rows else set()))
        raise ValueError(f"Zendesk CSV missing required columns: {missing}")
    return [
        {
            "id": str(row.get("id", "")),
            "subject": row.get("subject", "") or "",
            "description": row.get("description", "") or "",
            "status": row.get("status", "") or None,
            "created_at": _timestamp_or_none(row.get("created_at")),
            "tags": [part.strip() for part in (row.get("tags", "") or "").split(",") if part.strip()],
            "source": "zendesk",
        }
        for row in rows
        if row.get("description")
    ]


def _load_jira_json(path: Path) -> list[dict[str, Any]]:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        return []
    try:
        parsed = json.loads(text)
        raw_rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        raw_rows = [json.loads(line) for line in text.splitlines() if line.strip()]

    rows = []
    for item in raw_rows:
        fields = item.get("fields", {})
        status = fields.get("status") or {}
        description = fields.get("description") or ""
        if not description:
            continue
        rows.append(
            {
                "id": str(item.get("key", "")),
                "subject": fields.get("summary", "") or "",
                "description": description,
                "status": status.get("name"),
                "created_at": _timestamp_or_none(fields.get("created")),
                "tags": fields.get("labels") or [],
                "source": "jira",
            }
        )
    return rows


def _load_rows(source: Path) -> list[dict[str, Any]]:
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return _load_zendesk_csv(source)
    if suffix in {".json", ".jsonl"}:
        return _load_jira_json(source)
    raise ValueError(f"Unsupported ticket source extension: {source.suffix}")


def _write_arrow(table: pa.Table, path: Path) -> Path:
    with ipc.new_file(str(path), table.schema) as writer:
        writer.write(table)
    return path


def _write_faiss(vectors: np.ndarray, path: Path) -> Any:
    try:
        import faiss  # type: ignore
    except Exception:
        path.write_bytes(b"deterministic-faiss-unavailable\n")
        return None

    index = faiss.IndexFlatL2(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(path))
    return index


async def ingest_deterministic(ticket_source: Path, config: IngestAndRetrieveConfig) -> DeterministicIngestResult:
    started = time.perf_counter()
    out_dir = Path(config.output_path or "./sira-artifacts")
    out_dir.mkdir(parents=True, exist_ok=True)

    rows = _load_rows(Path(ticket_source))
    if not rows:
        raise ValueError("No ticket rows remain after deterministic ingest filtering")

    chunks = [f"{row['subject']} {row['description']}".strip() for row in rows]
    vectors = np.asarray([_hash_embedding(chunk) for chunk in chunks], dtype=np.float32)
    embeddings = vectors.tolist()

    table = pa.table(
        {
            "id": [row["id"] for row in rows],
            "subject": [row["subject"] for row in rows],
            "description": [row["description"] for row in rows],
            "status": [row["status"] for row in rows],
            "created_at": [row["created_at"] for row in rows],
            "tags": [row["tags"] for row in rows],
            "source": [row["source"] for row in rows],
            "chunk": chunks,
            "embedding": embeddings,
        }
    )

    arrow_path = _write_arrow(table, out_dir / "tickets.arrow")
    faiss_path = out_dir / "index.faiss"
    index = _write_faiss(vectors, faiss_path)

    elapsed = time.perf_counter() - started
    rows_ingested = len(rows)
    batches = math.ceil(rows_ingested / config.batch_size)
    return DeterministicIngestResult(
        table=table,
        index=index,
        metrics={
            "elapsed_s": elapsed,
            "rows_ingested": rows_ingested,
            "batches": batches,
            "throughput_rps": rows_ingested / elapsed if elapsed > 0 else 0.0,
        },
        artifacts={
            "arrow_path": str(arrow_path),
            "faiss_path": str(faiss_path),
        },
    )
