from __future__ import annotations

import asyncio

import numpy as np
import pyarrow as pa

from kb_ingestor.errors import BatchProcessingError, EmbedModelError
from kb_ingestor.models import IngestConfig


def _load_embedder(model_name: str):
    try:
        from sentence_transformers import SentenceTransformer

        return SentenceTransformer(model_name)
    except Exception as exc:  # pragma: no cover - exercised by tests via monkeypatch
        raise EmbedModelError(model_name, str(exc)) from exc


def _batch_ranges(total_rows: int, batch_size: int) -> list[tuple[int, int]]:
    ranges: list[tuple[int, int]] = []
    for start in range(0, total_rows, batch_size):
        stop = min(start + batch_size, total_rows)
        ranges.append((start, stop))
    return ranges


async def _embed_batch(
    batch_idx: int,
    batch_table: pa.Table,
    embedder,
    config: IngestConfig,
    semaphore: asyncio.Semaphore,
) -> tuple[int, pa.Table]:
    async with semaphore:
        chunks = batch_table.column("chunk").to_pylist()

        def _encode() -> np.ndarray:
            vectors = embedder.encode(chunks, convert_to_numpy=True, batch_size=config.batch_size)
            return np.asarray(vectors, dtype=np.float32)

        vectors = await asyncio.to_thread(_encode)
        embedding_array = pa.array(vectors.tolist(), type=pa.list_(pa.float32()))
        return batch_idx, batch_table.append_column("embedding", embedding_array)


async def embed(table: pa.Table, config: IngestConfig) -> pa.Table:
    embedder = _load_embedder(config.embed_model)
    semaphore = asyncio.Semaphore(config.max_workers)
    ranges = _batch_ranges(table.num_rows, config.batch_size)

    tasks = []
    for idx, (start, stop) in enumerate(ranges):
        tasks.append(_embed_batch(idx, table.slice(start, stop - start), embedder, config, semaphore))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    failed_batches: list[int] = []
    first_reason = "unknown"
    good: list[tuple[int, pa.Table]] = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            failed_batches.append(i)
            if first_reason == "unknown":
                first_reason = str(result)
        else:
            good.append(result)

    if failed_batches:
        raise BatchProcessingError(failed_batches, first_reason)

    ordered_tables = [tbl for _, tbl in sorted(good, key=lambda x: x[0])]
    return pa.concat_tables(ordered_tables) if ordered_tables else table.append_column(
        "embedding", pa.array([], type=pa.list_(pa.float32()))
    )
