"""L2 editor — applies patches to IngestorConfig."""
from __future__ import annotations

import dataclasses
from typing import Any

from ingestor import IngestorConfig


class L2Editor:
    VALID_KEYS = {f.name for f in dataclasses.fields(IngestorConfig)}
    CONSTRAINTS = {
        "max_chunk_tokens": (128, 1024),
        "min_chunk_chars": (10, 100),
        "chunk_overlap": (0, 200),
        "chunk_strategy": {"paragraph", "sliding_window", "sentence"},
    }

    def apply(self, config: IngestorConfig, patch: dict[str, Any]) -> IngestorConfig:
        clean: dict[str, Any] = {}
        for k, v in patch.items():
            if k not in self.VALID_KEYS:
                continue
            constraint = self.CONSTRAINTS.get(k)
            if isinstance(constraint, tuple):
                lo, hi = constraint
                v = max(lo, min(hi, v))
            elif isinstance(constraint, set):
                if v not in constraint:
                    continue
            clean[k] = v

        # Enforce chunk_overlap < max_chunk_tokens * 4
        max_t = clean.get("max_chunk_tokens", config.max_chunk_tokens)
        overlap = clean.get("chunk_overlap", config.chunk_overlap)
        if overlap >= max_t * 4:
            clean["chunk_overlap"] = max(0, max_t * 4 - 10)

        if not clean:
            return config
        return dataclasses.replace(config, **clean)

    def revert(self, config: IngestorConfig, prev: IngestorConfig) -> IngestorConfig:
        return prev
