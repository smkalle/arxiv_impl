from __future__ import annotations

import os
import tempfile
from pathlib import Path
from typing import Any

import numpy as np
import pyarrow as pa

from kb_ingestor.errors import EmbedDimMismatchError, FAISSWriteError, IngestSchemaError


def _embedding_matrix(table: pa.Table) -> np.ndarray:
    if "embedding" not in table.column_names:
        raise IngestSchemaError(["embedding"])
    matrix = np.array(table.column("embedding").to_pylist(), dtype=np.float32)
    if matrix.ndim != 2:
        raise IngestSchemaError(["embedding must be 2D list vectors"])
    return matrix


def _index_dim(index: Any) -> int:
    if hasattr(index, "d"):
        return int(index.d)
    raise IngestSchemaError(["index dimension attribute 'd' missing"])


def upsert(table: pa.Table, index: Any) -> tuple[pa.Table, Any]:
    embeddings = _embedding_matrix(table)
    dim = embeddings.shape[1]
    index_dim = _index_dim(index)
    if dim != index_dim:
        raise EmbedDimMismatchError(index_dim, dim)

    start_id = int(index.ntotal)
    index.add(embeddings)

    faiss_ids = pa.array(range(start_id, start_id + table.num_rows), type=pa.int64())
    out = table.append_column("faiss_id", faiss_ids)
    return out, index


def write_index_atomic(index: Any, out_path: Path) -> Path:
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        fd, tmp_name = tempfile.mkstemp(prefix=out_path.name + ".", dir=str(out_path.parent))
        os.close(fd)

        try:
            import faiss  # type: ignore

            faiss.write_index(index, tmp_name)
        except Exception:
            with open(tmp_name, "wb") as handle:
                payload = f"ntotal={getattr(index, 'ntotal', 0)}\n".encode("ascii")
                handle.write(payload)

        os.replace(tmp_name, str(out_path))
        return out_path
    except OSError as exc:
        raise FAISSWriteError(str(out_path), str(exc)) from exc
