"""StubBackend — deterministic pseudo-random vectors for tests."""
from __future__ import annotations
from typing import Any
import hashlib
import numpy as np
from .base import EmbeddingBackend


class StubBackend(EmbeddingBackend):
    """Returns deterministic vectors derived from input hash. No model loaded."""

    def __init__(self, embed_dim: int = 384):
        self._dim = embed_dim

    @property
    def name(self) -> str:
        return "stub"

    @property
    def embed_dim(self) -> int:
        return self._dim

    def embed(self, inputs: list[Any]) -> np.ndarray:
        vecs = []
        for item in inputs:
            key = str(item).encode() if not isinstance(item, bytes) else item
            seed = int(hashlib.md5(key).hexdigest()[:8], 16)
            rng = np.random.default_rng(seed)
            vec = rng.standard_normal(self._dim).astype(np.float32)
            vecs.append(vec)
        arr = np.stack(vecs)
        return self.l2_normalize(arr)
