from kb_ingestor.models import CANONICAL_TICKET_SCHEMA, IngestConfig, IngestResult


def test_canonical_schema_columns_and_types() -> None:
    names = CANONICAL_TICKET_SCHEMA.names
    assert names == ["id", "subject", "description", "status", "created_at", "tags", "source"]
    assert str(CANONICAL_TICKET_SCHEMA.field("id").type) == "string"
    assert str(CANONICAL_TICKET_SCHEMA.field("created_at").type) == "timestamp[us]"
    assert str(CANONICAL_TICKET_SCHEMA.field("tags").type) == "list<item: string>"


def test_ingest_config_defaults() -> None:
    cfg = IngestConfig()
    assert cfg.batch_size == 128
    assert cfg.max_workers == 4
    assert cfg.embed_model == "all-MiniLM-L6-v2"
    assert cfg.max_chunk_chars == 512
    assert cfg.min_chunk_chars == 20
    assert cfg.null_policy == "drop"
    assert cfg.faiss_factory == "Flat"
    assert cfg.output_path is None
    assert cfg.source_type == "auto"
    assert cfg.append is False


def test_ingest_result_defaults() -> None:
    result = IngestResult()
    assert result.table is None
    assert result.index is None
    assert result.metrics == {}
    assert result.artifacts == {}
