from kb_ingestor.api import ingest
from kb_ingestor.errors import (
    BatchProcessingError,
    EmbedDimMismatchError,
    EmbedModelError,
    FAISSWriteError,
    IngestNullError,
    IngestSchemaError,
)
from kb_ingestor.models import CANONICAL_TICKET_SCHEMA, IngestConfig, IngestResult

__all__ = [
    "ingest",
    "IngestConfig",
    "IngestResult",
    "CANONICAL_TICKET_SCHEMA",
    "IngestSchemaError",
    "IngestNullError",
    "EmbedModelError",
    "EmbedDimMismatchError",
    "FAISSWriteError",
    "BatchProcessingError",
]
