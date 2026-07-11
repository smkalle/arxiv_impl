"""JinaAPIBackend — calls api.jina.ai/v1/embeddings via httpx."""
from __future__ import annotations
from typing import Any
from pathlib import Path
import base64
import numpy as np
import httpx
from .base import EmbeddingBackend


JINA_API_URL = "https://api.jina.ai/v1/embeddings"


class JinaAPIBackend(EmbeddingBackend):

    def __init__(
        self,
        api_key: str,
        model: str = "jina-embeddings-v5-omni-small",
        task: str = "retrieval.passage",
        dimensions: int = 512,
        timeout: float = 30.0,
    ):
        self._api_key = api_key
        self._model = model
        self._task = task
        self._dim = dimensions
        self._timeout = timeout

    @property
    def name(self) -> str:
        return "jina_api"

    @property
    def embed_dim(self) -> int:
        return self._dim

    def embed(self, inputs: list[Any]) -> np.ndarray:
        payload_inputs = []
        for item in inputs:
            if isinstance(item, str):
                payload_inputs.append({"text": item})
            elif isinstance(item, Path):
                # Read file and base64-encode
                data = item.read_bytes()
                b64 = base64.b64encode(data).decode()
                suffix = item.suffix.lower()
                mime = "image/jpeg" if suffix in (".jpg", ".jpeg") else "image/png"
                payload_inputs.append({"image": f"data:{mime};base64,{b64}"})
            else:
                payload_inputs.append({"text": str(item)})

        payload = {
            "model": self._model,
            "task": self._task,
            "dimensions": self._dim,
            "input": payload_inputs,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        resp = httpx.post(JINA_API_URL, json=payload, headers=headers, timeout=self._timeout)
        resp.raise_for_status()
        data = resp.json()

        vecs = np.array(
            [item["embedding"] for item in data["data"]],
            dtype=np.float32,
        )
        return self.l2_normalize(vecs)
