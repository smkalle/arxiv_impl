"""LocalBackend — SentenceTransformer model, runs on CPU/GPU."""
from __future__ import annotations
from typing import Any
from pathlib import Path
import numpy as np
from .base import EmbeddingBackend


class LocalBackend(EmbeddingBackend):

    def __init__(self, model_id: str = "all-MiniLM-L6-v2", embed_dim: int | None = None):
        from sentence_transformers import SentenceTransformer
        self._model_id = model_id
        # trust_remote_code needed for jina models
        trust = "jina" in model_id.lower()
        self._model = SentenceTransformer(model_id, trust_remote_code=trust)
        natural_dim = self._model.get_sentence_embedding_dimension()
        self._dim = embed_dim if embed_dim and embed_dim <= natural_dim else natural_dim
        self._uses_jina_retrieval_prompts = "jina-embeddings-v5" in model_id.lower() and "retrieval" in model_id.lower()

    @property
    def name(self) -> str:
        return "local"

    @property
    def embed_dim(self) -> int:
        return self._dim

    def embed(self, inputs: list[Any]) -> np.ndarray:
        return self._embed(inputs, prompt_name="document")

    def embed_query(self, query: str) -> np.ndarray:
        return self._embed([query], prompt_name="query")[0]

    def _embed(self, inputs: list[Any], prompt_name: str | None = None) -> np.ndarray:
        text_inputs = []
        for item in inputs:
            if isinstance(item, str):
                text_inputs.append(item)
            elif isinstance(item, Path):
                # For non-text assets: use path string as text proxy (v1)
                text_inputs.append(str(item))
            else:
                # PIL Image or other — use str repr as proxy (v1; jina-omni handles natively)
                text_inputs.append(str(item))

        encode_kwargs = {
            "normalize_embeddings": True,
            "show_progress_bar": False,
            "convert_to_numpy": True,
        }
        if self._uses_jina_retrieval_prompts and prompt_name:
            encode_kwargs["prompt_name"] = prompt_name

        vecs = self._model.encode(text_inputs, **encode_kwargs).astype(np.float32)

        # Matryoshka truncation if requested
        if self._dim < vecs.shape[1]:
            vecs = vecs[:, :self._dim]
            vecs = self.l2_normalize(vecs)

        return vecs
