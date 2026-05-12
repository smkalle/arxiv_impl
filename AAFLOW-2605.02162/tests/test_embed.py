import asyncio
import importlib

import numpy as np
import pyarrow as pa
import pytest

from kb_ingestor.errors import BatchProcessingError, EmbedModelError
from kb_ingestor.models import IngestConfig
embed_module = importlib.import_module("kb_ingestor.ops.embed")
embed_op = embed_module.embed


class FakeEmbedder:
    def __init__(self, dim: int = 4, fail_on: str | None = None):
        self.dim = dim
        self.fail_on = fail_on
        self.calls: list[list[str]] = []

    def encode(self, chunks, convert_to_numpy=True, batch_size=128):
        self.calls.append(list(chunks))
        if self.fail_on is not None and self.fail_on in chunks:
            raise RuntimeError("forced batch failure")
        out = []
        for text in chunks:
            base = float(len(text))
            out.append([base + i for i in range(self.dim)])
        return np.array(out, dtype=np.float32)


def _input_table() -> pa.Table:
    return pa.table(
        {
            "id": ["1", "2", "3", "4", "5"],
            "chunk": ["alpha", "beta", "gamma", "delta", "epsilon"],
        }
    )


def test_embed_output_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder(dim=3)
    monkeypatch.setattr(embed_module, "_load_embedder", lambda _: fake)

    out = asyncio.run(embed_op(_input_table(), IngestConfig(batch_size=2, max_workers=2)))
    assert out.num_rows == 5
    assert "embedding" in out.column_names
    assert str(out.schema.field("embedding").type) == "list<item: float>"
    first = out.column("embedding")[0].as_py()
    assert len(first) == 3


def test_embed_preserves_row_order(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder(dim=2)
    monkeypatch.setattr(embed_module, "_load_embedder", lambda _: fake)
    out = asyncio.run(embed_op(_input_table(), IngestConfig(batch_size=2, max_workers=3)))
    assert out.column("id").to_pylist() == ["1", "2", "3", "4", "5"]


def test_embed_batching_respects_batch_size(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder(dim=2)
    monkeypatch.setattr(embed_module, "_load_embedder", lambda _: fake)
    asyncio.run(embed_op(_input_table(), IngestConfig(batch_size=2, max_workers=2)))
    # 5 rows with batch_size=2 -> 3 calls
    assert len(fake.calls) == 3
    assert fake.calls[0] == ["alpha", "beta"]


def test_embed_model_load_failure_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(_: str):
        raise EmbedModelError("all-MiniLM-L6-v2", "boom")

    monkeypatch.setattr(embed_module, "_load_embedder", _raise)
    with pytest.raises(EmbedModelError):
        asyncio.run(embed_op(_input_table(), IngestConfig()))


def test_embed_batch_failure_raises_summary(monkeypatch: pytest.MonkeyPatch) -> None:
    fake = FakeEmbedder(dim=2, fail_on="gamma")
    monkeypatch.setattr(embed_module, "_load_embedder", lambda _: fake)
    with pytest.raises(BatchProcessingError) as exc:
        asyncio.run(embed_op(_input_table(), IngestConfig(batch_size=2, max_workers=2)))
    assert exc.value.failed_batches == [1]


def test_embed_uses_async_concurrency_path(monkeypatch: pytest.MonkeyPatch) -> None:
    # Patch to_thread to observe usage without altering behavior.
    called = {"count": 0}
    real_to_thread = asyncio.to_thread

    async def wrapped_to_thread(fn, *args, **kwargs):
        called["count"] += 1
        return await real_to_thread(fn, *args, **kwargs)

    fake = FakeEmbedder(dim=2)
    monkeypatch.setattr(embed_module, "_load_embedder", lambda _: fake)
    monkeypatch.setattr(embed_module.asyncio, "to_thread", wrapped_to_thread)

    asyncio.run(embed_op(_input_table(), IngestConfig(batch_size=2, max_workers=2)))
    assert called["count"] == 3
