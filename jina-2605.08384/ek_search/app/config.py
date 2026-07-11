"""Configuration — loaded from environment / .env file."""
from __future__ import annotations
import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class Settings:
    # Backend
    embedding_backend: str = "stub"          # stub | local | jina_api
    local_model_id: str = "all-MiniLM-L6-v2"
    jina_api_key: str = ""
    jina_model: str = "jina-embeddings-v5-omni-small"
    jina_task: str = "retrieval.passage"
    jina_dimensions: int = 512

    # Embedding
    embed_dim: int = 384
    task_adapter: str = "retrieval"

    # Chroma
    chroma_path: str = "./data/chroma"
    chroma_collection: str = "multimodal-knowledge"

    # Ingestion
    ingest_batch_size: int = 32
    ingest_max_retries: int = 3

    # API
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Settings":
        """Load settings from environment variables (uppercase names)."""
        # Try to load .env if python-dotenv available
        try:
            from dotenv import load_dotenv
            env_path = Path(__file__).parent.parent / ".env"
            if env_path.exists():
                load_dotenv(env_path)
        except ImportError:
            pass

        return cls(
            embedding_backend=os.getenv("EMBEDDING_BACKEND", "stub"),
            local_model_id=os.getenv("LOCAL_MODEL_ID", "all-MiniLM-L6-v2"),
            jina_api_key=os.getenv("JINA_API_KEY", ""),
            jina_model=os.getenv("JINA_MODEL", "jina-embeddings-v5-omni-small"),
            jina_task=os.getenv("JINA_TASK", "retrieval.passage"),
            jina_dimensions=int(os.getenv("JINA_DIMENSIONS", "512")),
            embed_dim=int(os.getenv("EMBED_DIM", "384")),
            task_adapter=os.getenv("TASK_ADAPTER", "retrieval"),
            chroma_path=os.getenv("CHROMA_PATH", "./data/chroma"),
            chroma_collection=os.getenv("CHROMA_COLLECTION", "multimodal-knowledge"),
            ingest_batch_size=int(os.getenv("INGEST_BATCH_SIZE", "32")),
            ingest_max_retries=int(os.getenv("INGEST_MAX_RETRIES", "3")),
            api_host=os.getenv("API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("API_PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


# Module-level singleton — can be overridden in tests
_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings.from_env()
    return _settings


def override_settings(s: Settings) -> None:
    """Override global settings (for tests)."""
    global _settings
    _settings = s


def reset_settings() -> None:
    """Reset to env-loaded settings (for tests)."""
    global _settings
    _settings = None
