"""Iteration 1 — pipeline tests."""
import pytest
from app.ingestion.pipeline import IngestionPipeline
from app.ingestion.preprocessor import DocumentPreprocessor


def test_pipeline_ingest_basic(tmp_chroma, stub_backend, sample_docs):
    pipeline = IngestionPipeline(backend=stub_backend, store=tmp_chroma)
    result = pipeline.ingest_documents(sample_docs)
    assert result.status == "ok"
    assert result.ingested >= len(sample_docs)
    assert result.failed == 0
    assert tmp_chroma.count() >= len(sample_docs)


def test_pipeline_idempotency(tmp_chroma, stub_backend, sample_docs):
    pipeline = IngestionPipeline(backend=stub_backend, store=tmp_chroma)
    pipeline.ingest_documents(sample_docs)
    count_after_first = tmp_chroma.count()

    result2 = pipeline.ingest_documents(sample_docs)
    count_after_second = tmp_chroma.count()

    assert count_after_first == count_after_second
    assert result2.skipped >= len(sample_docs)
    assert result2.ingested == 0


def test_pipeline_duration_tracked(tmp_chroma, stub_backend, sample_docs):
    pipeline = IngestionPipeline(backend=stub_backend, store=tmp_chroma)
    result = pipeline.ingest_documents(sample_docs)
    assert result.duration_ms > 0


def test_pipeline_empty(tmp_chroma, stub_backend):
    pipeline = IngestionPipeline(backend=stub_backend, store=tmp_chroma)
    result = pipeline.ingest_documents([])
    assert result.ingested == 0
    assert result.failed == 0


def test_pipeline_batch_size(tmp_chroma, stub_backend, sample_docs):
    # Batch size smaller than docs count
    pipeline = IngestionPipeline(backend=stub_backend, store=tmp_chroma, batch_size=1)
    result = pipeline.ingest_documents(sample_docs)
    assert result.ingested >= len(sample_docs)
    assert result.failed == 0


def test_pipeline_acl_groups(tmp_chroma, stub_backend, sample_docs):
    pipeline = IngestionPipeline(backend=stub_backend, store=tmp_chroma)
    pipeline.ingest_documents(sample_docs, acl_groups=["eng-team"])
    # Verify stored correctly
    stats = tmp_chroma.stats()
    assert stats["total_chunks"] >= len(sample_docs)
