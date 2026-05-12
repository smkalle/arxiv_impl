class IngestError(Exception):
    """Base class for ingest pipeline failures."""


class IngestSchemaError(IngestError):
    def __init__(self, missing_columns: list[str]):
        self.missing_columns = missing_columns
        message = f"Missing required columns: {', '.join(missing_columns)}"
        super().__init__(message)


class IngestNullError(IngestError):
    def __init__(self, row_ids: list[str | int]):
        self.row_ids = row_ids
        message = f"Null description rows found for ids: {', '.join(map(str, row_ids))}"
        super().__init__(message)


class EmbedModelError(IngestError):
    def __init__(self, model_name: str, reason: str):
        self.model_name = model_name
        self.reason = reason
        super().__init__(f"Failed to load embed model '{model_name}': {reason}")


class EmbedDimMismatchError(IngestError):
    def __init__(self, expected_dim: int, actual_dim: int):
        self.expected_dim = expected_dim
        self.actual_dim = actual_dim
        super().__init__(f"Embedding dimension mismatch: expected {expected_dim}, got {actual_dim}")


class FAISSWriteError(IngestError):
    def __init__(self, path: str, reason: str):
        self.path = path
        self.reason = reason
        super().__init__(f"Failed to write FAISS index at '{path}': {reason}")


class BatchProcessingError(IngestError):
    def __init__(self, failed_batches: list[int], reason: str):
        self.failed_batches = failed_batches
        self.reason = reason
        batch_text = ", ".join(map(str, failed_batches))
        super().__init__(f"Batch processing failed for batches [{batch_text}]: {reason}")
