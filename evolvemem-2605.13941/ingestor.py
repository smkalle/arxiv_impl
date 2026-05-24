"""
KB Ingestor — reads kb_articles.csv and ingests into SimpleMem (or stub).

IngestorConfig is L2's edit target: chunking strategy, chunk size, overlap.
The synthesis_ratio (chunks_added / articles_read) is L2's fitness signal.
"""
from __future__ import annotations

import csv
import dataclasses
import json
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class IngestorConfig:
    """L2's edit target: controls how articles are chunked before ingestion."""
    chunk_strategy: str = "paragraph"   # "paragraph" | "sliding_window" | "sentence"
    max_chunk_tokens: int = 400
    min_chunk_chars: int = 20
    chunk_overlap: int = 50
    add_product_area_entity: bool = False
    max_parallel_workers: int = 4

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "IngestorConfig":
        valid = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in valid})

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


class KBIngestor:
    def __init__(self, router: Any, config: IngestorConfig | None = None) -> None:
        self._router = router
        self._config = config or IngestorConfig()
        self._last_stats: dict[str, Any] = {}

    def ingest_csv(self, csv_path: Path) -> dict[str, Any]:
        """Read kb_articles.csv, chunk bodies, add_dialogue per chunk."""
        articles_read = 0
        chunks_added = 0
        skipped = 0

        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                kb_id = row.get("kb_id", "")
                title = row.get("title", "")
                body = row.get("body", "")
                product_area = row.get("product_area", "")
                tags_raw = row.get("tags", "")

                if not body.strip():
                    skipped += 1
                    continue

                articles_read += 1
                tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
                if self._config.add_product_area_entity and product_area:
                    tags.append(product_area)

                chunks = self._chunk(body)
                for chunk in chunks:
                    if len(chunk) < self._config.min_chunk_chars:
                        continue
                    self._router.add_dialogue(
                        user=f"{title}. {chunk}",
                        assistant=body,
                        metadata={
                            "article_id": kb_id,
                            "title": title,
                            "product_area": product_area,
                            "tags": tags,
                        },
                    )
                    chunks_added += 1

        stats = {
            "articles_read": articles_read,
            "chunks_added": chunks_added,
            "skipped": skipped,
            "synthesis_ratio": (
                round(chunks_added / articles_read, 4) if articles_read > 0 else 0.0
            ),
        }
        self._last_stats = stats
        return stats

    def finalize(self) -> None:
        self._router.finalize()

    @property
    def synthesis_ratio(self) -> float:
        return self._last_stats.get("synthesis_ratio", 0.0)

    @property
    def last_stats(self) -> dict[str, Any]:
        return dict(self._last_stats)

    # ── Chunking strategies ──────────────────────────────────────────────────

    def _chunk(self, text: str) -> list[str]:
        strategy = self._config.chunk_strategy
        if strategy == "paragraph":
            return self._chunk_paragraph(text)
        if strategy == "sliding_window":
            return self._chunk_sliding_window(text)
        if strategy == "sentence":
            return self._chunk_sentences(text)
        return [text]

    def _chunk_paragraph(self, text: str) -> list[str]:
        """Split on double newline or numbered steps."""
        import re
        parts = re.split(r"\n\n+|(?<=[.!?])\s{2,}", text)
        chunks = []
        buf = ""
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if len(buf) + len(part) <= self._config.max_chunk_tokens * 4:
                buf = (buf + " " + part).strip()
            else:
                if buf:
                    chunks.append(buf)
                buf = part
        if buf:
            chunks.append(buf)
        return chunks or [text]

    def _chunk_sliding_window(self, text: str) -> list[str]:
        """Fixed-size character windows with overlap."""
        size = self._config.max_chunk_tokens * 4  # rough chars-per-token estimate
        overlap = self._config.chunk_overlap * 4
        if len(text) <= size:
            return [text]
        chunks = []
        start = 0
        while start < len(text):
            end = min(start + size, len(text))
            chunks.append(text[start:end])
            start += size - overlap
        return chunks

    def _chunk_sentences(self, text: str) -> list[str]:
        """Group sentences into chunks up to max_chunk_tokens."""
        import re
        sentences = re.split(r"(?<=[.!?])\s+", text)
        chunks = []
        buf = ""
        for s in sentences:
            s = s.strip()
            if not s:
                continue
            if len(buf) + len(s) <= self._config.max_chunk_tokens * 4:
                buf = (buf + " " + s).strip()
            else:
                if buf:
                    chunks.append(buf)
                buf = s
        if buf:
            chunks.append(buf)
        return chunks or [text]


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))
    from config import (
        KB_ARTICLES_CSV, LANCEDB_DIR, INGESTOR_DEFAULTS,
        SIMPLEMEM_USE_STUB,
    )
    from simplemem_router import SimplememRouter
    import config as cfg

    class _FakeSettings:
        simplemem_use_stub = getattr(cfg, "SIMPLEMEM_USE_STUB", True)
        lancedb_uri = str(LANCEDB_DIR)

    router = SimplememRouter(_FakeSettings())
    router.create("text")

    ingestor_cfg = IngestorConfig(**{
        k: v for k, v in INGESTOR_DEFAULTS.items()
        if k in {f.name for f in dataclasses.fields(IngestorConfig)}
    })
    ingestor = KBIngestor(router, ingestor_cfg)
    stats = ingestor.ingest_csv(KB_ARTICLES_CSV)
    ingestor.finalize()

    print(f"Ingest complete:")
    print(f"  articles_read : {stats['articles_read']}")
    print(f"  chunks_added  : {stats['chunks_added']}")
    print(f"  synthesis_ratio: {stats['synthesis_ratio']:.3f}")
