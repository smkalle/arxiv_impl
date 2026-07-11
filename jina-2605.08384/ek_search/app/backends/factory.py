"""Factory — returns correct EmbeddingBackend from config."""
from __future__ import annotations
from .base import EmbeddingBackend


def get_backend(settings=None) -> EmbeddingBackend:
    if settings is None:
        from app.config import get_settings
        settings = get_settings()

    backend = settings.embedding_backend.lower()

    if backend == "stub":
        from .stub import StubBackend
        return StubBackend(embed_dim=settings.embed_dim)

    if backend == "local":
        from .local import LocalBackend
        return LocalBackend(model_id=settings.local_model_id, embed_dim=settings.embed_dim)

    if backend == "jina_api":
        from .jina_api import JinaAPIBackend
        return JinaAPIBackend(
            api_key=settings.jina_api_key,
            model=settings.jina_model,
            task=settings.jina_task,
            dimensions=settings.jina_dimensions,
        )

    raise ValueError(f"Unknown EMBEDDING_BACKEND: {backend!r}. Choose: stub | local | jina_api")
