from kb_ingestor.errors import (
    BatchProcessingError,
    EmbedDimMismatchError,
    EmbedModelError,
    FAISSWriteError,
    IngestNullError,
    IngestSchemaError,
)


def test_ingest_schema_error_message() -> None:
    err = IngestSchemaError(["id", "description"])
    assert "Missing required columns" in str(err)
    assert "id" in str(err)


def test_ingest_null_error_message() -> None:
    err = IngestNullError([1, "T-22"])
    assert "Null description rows" in str(err)
    assert "T-22" in str(err)


def test_embed_model_error_message() -> None:
    err = EmbedModelError("all-MiniLM-L6-v2", "network timeout")
    assert "Failed to load embed model" in str(err)
    assert "network timeout" in str(err)


def test_embed_dim_mismatch_error_message() -> None:
    err = EmbedDimMismatchError(384, 768)
    assert "expected 384" in str(err)
    assert "got 768" in str(err)


def test_faiss_write_error_message() -> None:
    err = FAISSWriteError("/tmp/index.faiss", "disk full")
    assert "/tmp/index.faiss" in str(err)
    assert "disk full" in str(err)


def test_batch_processing_error_message() -> None:
    err = BatchProcessingError([0, 2], "encoder crashed")
    assert "[0, 2]" in str(err)
    assert "encoder crashed" in str(err)
