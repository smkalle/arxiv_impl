"""EmbeddingBackend ABC."""
from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Any
import numpy as np


class EmbeddingBackend(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @property
    @abstractmethod
    def embed_dim(self) -> int: ...

    @abstractmethod
    def embed(self, inputs: list[Any]) -> np.ndarray:
        """Embed mixed list of str | PIL.Image | Path.
        Returns float32 ndarray (n, embed_dim), L2-normalized."""
        ...

    def embed_query(self, query: str) -> np.ndarray:
        return self.embed([query])[0]

    @staticmethod
    def l2_normalize(arr: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(arr, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1e-8, norms)
        return arr / norms
