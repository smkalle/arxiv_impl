"""Iteration 1 — vector store tests."""
import numpy as np
import pytest
from app.models import Chunk
from app.vector_store import ChromaVectorStore


def make_chunk(idx: int, text: str = "sample text") -> Chunk:
    return Chunk(
        id=f"src:test:doc{idx}:chunk_0",
        document_id=f"src:test:doc{idx}",
        content=text,
        modality="text",
        source_system="test",
        asset_url=f"/test/doc{idx}",
        chunk_index=0,
    )


def make_embedding(dim: int = 64) -> np.ndarray:
    v = np.random.default_rng(42).random(dim).astype(np.float32)
    return v / np.linalg.norm(v)


def test_add_and_count(tmp_chroma):
    chunks = [make_chunk(i, f"document content {i}") for i in range(3)]
    embs = np.stack([make_embedding() for _ in range(3)])
    added = tmp_chroma.add_chunks(chunks, embs)
    assert added == 3
    assert tmp_chroma.count() == 3


def test_query_returns_results(tmp_chroma):
    chunks = [make_chunk(i, f"text {i}") for i in range(5)]
    embs = np.stack([make_embedding() for _ in range(5)])
    tmp_chroma.add_chunks(chunks, embs)

    query_vec = make_embedding()
    results = tmp_chroma.query(query_vec, n_results=3)
    assert len(results) == 3
    for r in results:
        assert 0.0 <= r.score <= 1.0


def test_upsert_idempotency(tmp_chroma):
    chunk = make_chunk(1, "unique content")
    emb = np.stack([make_embedding()])
    tmp_chroma.add_chunks([chunk], emb)
    tmp_chroma.add_chunks([chunk], emb)   # upsert same id
    assert tmp_chroma.count() == 1        # still 1


def test_delete_by_document(tmp_chroma):
    chunks = [
        Chunk(id=f"src:test:docA:chunk_{i}", document_id="src:test:docA",
              content=f"chunk {i}", modality="text", source_system="test", asset_url="/a")
        for i in range(3)
    ]
    embs = np.stack([make_embedding() for _ in range(3)])
    tmp_chroma.add_chunks(chunks, embs)
    assert tmp_chroma.count() == 3
    deleted = tmp_chroma.delete_by_document("src:test:docA")
    assert deleted == 3
    assert tmp_chroma.count() == 0


def test_modality_filter(tmp_chroma):
    text_chunk = make_chunk(1, "text document")
    img_chunk = Chunk(id="src:test:img:chunk_0", document_id="src:test:img",
                      content="image", modality="image",
                      source_system="test", asset_url="/img.png")
    embs = np.stack([make_embedding(), make_embedding()])
    tmp_chroma.add_chunks([text_chunk, img_chunk], embs)

    q = make_embedding()
    text_results = tmp_chroma.query(q, n_results=5, modality_filter=["text"])
    assert all(r.modality == "text" for r in text_results)


def test_stats(tmp_chroma):
    chunks = [make_chunk(i) for i in range(4)]
    embs = np.stack([make_embedding() for _ in range(4)])
    tmp_chroma.add_chunks(chunks, embs)
    s = tmp_chroma.stats()
    assert s["total_chunks"] == 4
    assert "text" in s["by_modality"]
    assert "test" in s["by_source"]


def test_empty_query(tmp_chroma):
    # Query empty store returns empty list (not error)
    q = make_embedding()
    results = tmp_chroma.query(q, n_results=5)
    assert results == []


def test_clear(tmp_chroma):
    chunks = [make_chunk(i) for i in range(3)]
    embs = np.stack([make_embedding() for _ in range(3)])
    tmp_chroma.add_chunks(chunks, embs)
    tmp_chroma.clear()
    assert tmp_chroma.count() == 0
