from pathlib import Path
import importlib

import numpy as np
import pyarrow as pa
import pytest

from kb_ingestor.errors import EmbedDimMismatchError, FAISSWriteError
from kb_ingestor.ops.upsert import upsert, write_index_atomic

upsert_module = importlib.import_module("kb_ingestor.ops.upsert")


class FakeIndex:
    def __init__(self, dim: int):
        self.d = dim
        self.ntotal = 0
        self.add_calls = 0

    def add(self, embeddings: np.ndarray) -> None:
        self.add_calls += 1
        if embeddings.shape[1] != self.d:
            raise ValueError("dimension mismatch")
        self.ntotal += embeddings.shape[0]


def _table_with_embeddings(values: list[list[float]], ids: list[str] | None = None) -> pa.Table:
    row_ids = ids if ids is not None else [str(i) for i in range(len(values))]
    return pa.table({"id": row_ids, "embedding": values})


def test_faiss_id_contiguous() -> None:
    index = FakeIndex(4)
    table = _table_with_embeddings(
        [
            [1.0, 0.0, 0.0, 0.0],
            [0.0, 1.0, 0.0, 0.0],
            [0.0, 0.0, 1.0, 0.0],
        ],
        ["a", "b", "c"],
    )

    out, out_index = upsert(table, index)
    assert out.num_rows == 3
    assert str(out.schema.field("faiss_id").type) == "int64"
    assert out.column("faiss_id").to_pylist() == [0, 1, 2]
    assert out_index.ntotal == 3


def test_append_mode() -> None:
    index = FakeIndex(4)
    first = _table_with_embeddings([[1, 0, 0, 0], [0, 1, 0, 0]], ["1", "2"])
    second = _table_with_embeddings([[0, 0, 1, 0], [0, 0, 0, 1], [1, 1, 0, 0]], ["3", "4", "5"])

    _, index = upsert(first, index)
    out, index = upsert(second, index)
    assert out.column("faiss_id").to_pylist() == [2, 3, 4]
    assert index.ntotal == 5


def test_dim_mismatch_raises() -> None:
    index = FakeIndex(4)
    table = _table_with_embeddings([[1, 2, 3, 4, 5]], ["x"])
    before = index.ntotal
    with pytest.raises(EmbedDimMismatchError):
        upsert(table, index)
    assert index.ntotal == before


def test_write_failure_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    index = FakeIndex(4)
    arr = np.array([[1.0, 0.0, 0.0, 0.0]], dtype=np.float32)
    index.add(arr)

    def fail_replace(_src: str, _dst: str) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(upsert_module.os, "replace", fail_replace)
    with pytest.raises(FAISSWriteError) as exc:
        write_index_atomic(index, tmp_path / "index.faiss")
    assert "disk full" in str(exc.value)


def test_embedding_dtype_cast_to_float32() -> None:
    index = FakeIndex(3)
    table = _table_with_embeddings([[1.1, 2.2, 3.3], [4.4, 5.5, 6.6]], ["a", "b"])
    out, index = upsert(table, index)
    assert index.ntotal == 2
    assert out.column("faiss_id").to_pylist() == [0, 1]
