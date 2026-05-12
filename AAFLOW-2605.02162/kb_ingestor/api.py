from __future__ import annotations

import json
import time
from pathlib import Path

import pyarrow as pa
import pyarrow.ipc as ipc

from kb_ingestor.models import IngestConfig, IngestResult
from kb_ingestor.ops.chunk import chunk
from kb_ingestor.ops.embed import embed
from kb_ingestor.ops.load import load
from kb_ingestor.ops.upsert import upsert, write_index_atomic


def _write_arrow_table(table: pa.Table, out_path: Path) -> Path:
    with ipc.new_file(str(out_path), table.schema) as writer:
        writer.write(table)
    return out_path


def _write_run_summary(summary_path: Path, payload: dict) -> Path:
    summary_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return summary_path


def _build_index(embed_dim: int):
    import faiss  # type: ignore

    return faiss.IndexFlatL2(embed_dim)


async def ingest(source: Path | pa.Table, config: IngestConfig) -> IngestResult:
    started = time.perf_counter()

    loaded = load(source, config)
    chunked = chunk(loaded, config)
    embedded = await embed(chunked, config)

    if embedded.num_rows == 0:
        raise ValueError("No rows remain after chunk filtering; cannot build index")

    embed_dim = len(embedded.column("embedding")[0].as_py())

    index = _build_index(embed_dim)
    upserted, index = upsert(embedded, index)

    elapsed = time.perf_counter() - started
    metrics = {
        "elapsed_s": elapsed,
        "rows_ingested": upserted.num_rows,
        "batches": (upserted.num_rows + config.batch_size - 1) // config.batch_size,
        "throughput_rps": (upserted.num_rows / elapsed) if elapsed > 0 else 0.0,
    }

    artifacts: dict[str, str] = {}
    if config.output_path is not None:
        out_dir = Path(config.output_path)
        out_dir.mkdir(parents=True, exist_ok=True)

        arrow_path = _write_arrow_table(upserted, out_dir / "tickets.arrow")
        faiss_path = write_index_atomic(index, out_dir / "index.faiss")
        summary_path = _write_run_summary(
            out_dir / "run_summary.json",
            {
                "rows_ingested": upserted.num_rows,
                "batches": metrics["batches"],
                "elapsed_s": metrics["elapsed_s"],
                "throughput_rps": metrics["throughput_rps"],
                "embed_dim": embed_dim,
            },
        )
        artifacts = {
            "arrow_path": str(arrow_path),
            "faiss_path": str(faiss_path),
            "run_summary_path": str(summary_path),
        }

    return IngestResult(table=upserted, index=index, metrics=metrics, artifacts=artifacts)
