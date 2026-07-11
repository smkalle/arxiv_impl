"""Iteration 1 — preprocessor tests."""
import pytest
from app.ingestion.preprocessor import DocumentPreprocessor, chunk_text
from app.models import Document


def test_chunk_text_basic():
    text = " ".join([f"word{i}" for i in range(100)])
    chunks = chunk_text(text, "doc1", chunk_size=32, overlap=8)
    assert len(chunks) > 1
    for text_str, idx, tcount in chunks:
        assert tcount <= 32
        assert len(text_str) > 0


def test_chunk_text_overlap():
    words = [f"w{i}" for i in range(50)]
    text = " ".join(words)
    chunks = chunk_text(text, "doc1", chunk_size=20, overlap=5)
    # Second chunk should start before end of first
    if len(chunks) >= 2:
        first_words = set(chunks[0][0].split())
        second_words = set(chunks[1][0].split())
        assert len(first_words & second_words) > 0  # overlap exists


def test_chunk_text_short():
    text = "just a few words"
    chunks = chunk_text(text, "doc1", chunk_size=512, overlap=64)
    assert len(chunks) == 1
    assert chunks[0][0] == text


def test_chunk_text_empty():
    chunks = chunk_text("", "doc1")
    assert chunks == []


def test_process_text_doc():
    proc = DocumentPreprocessor(text_chunk_size=50, text_overlap=10)
    doc = Document(
        id="src:test:doc1",
        content="word " * 200,
        modality="text",
        source_system="test",
        asset_url="/test",
    )
    chunks = proc.process(doc)
    assert len(chunks) > 1
    for c in chunks:
        assert c.modality == "text"
        assert c.document_id == "src:test:doc1"
        assert c.source_system == "test"


def test_process_short_text():
    proc = DocumentPreprocessor()
    doc = Document(id="d", content="short text", modality="text", source_system="t", asset_url="/")
    chunks = proc.process(doc)
    assert len(chunks) == 1
    assert chunks[0].content == "short text"


def test_process_image():
    from pathlib import Path
    proc = DocumentPreprocessor()
    doc = Document(id="src:test:img", content=Path("/fake/image.png"),
                   modality="image", source_system="test", asset_url="/img.png")
    chunks = proc.process(doc)
    assert len(chunks) == 1
    assert chunks[0].modality == "image"


def test_chunk_ids_sequential():
    proc = DocumentPreprocessor(text_chunk_size=10, text_overlap=2)
    doc = Document(id="src:test:d", content="word " * 50,
                   modality="text", source_system="test", asset_url="/")
    chunks = proc.process(doc)
    for i, c in enumerate(chunks):
        assert f":chunk_{i}" in c.id


def test_acl_groups_passed():
    proc = DocumentPreprocessor()
    doc = Document(id="d", content="content", modality="text", source_system="t", asset_url="/")
    chunks = proc.process(doc, acl_groups=["eng", "design"])
    assert chunks[0].acl_groups == ["eng", "design"]


def test_metadata_for_chroma():
    proc = DocumentPreprocessor()
    doc = Document(id="d", content="hello world", modality="text",
                   source_system="test", asset_url="/test")
    chunks = proc.process(doc)
    meta = chunks[0].metadata_for_chroma()
    assert meta["modality"] == "text"
    assert meta["source_system"] == "test"
    assert "acl_groups" in meta
    assert "content_hash" in meta
