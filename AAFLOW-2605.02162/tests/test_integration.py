import asyncio
import importlib
import json
from pathlib import Path

import pyarrow as pa

from kb_ingestor.api import ingest
from kb_ingestor.cli import cli
from kb_ingestor.models import IngestConfig


class FakeEmbedder:
    def encode(self, chunks, convert_to_numpy=True, batch_size=128):
        return [[float(len(c)), float(len(c)) + 1.0, float(len(c)) + 2.0] for c in chunks]


def _patch_embedder(monkeypatch):
    embed_mod = importlib.import_module("kb_ingestor.ops.embed")
    monkeypatch.setattr(embed_mod, "_load_embedder", lambda _name: FakeEmbedder())


def test_e2e_zendesk_1k(tmp_path: Path, monkeypatch) -> None:
    _patch_embedder(monkeypatch)
    src = tmp_path / "tickets.csv"
    src.write_text(
        "id,subject,description,status,created_at,tags\n"
        + "\n".join([f"Z-{i},Subject {i},Description {i} with enough chars,open,2026-01-01T10:00:00Z,tag{i%10}" for i in range(1000)])
        + "\n",
        encoding="utf-8",
    )
    out = tmp_path / "out"
    result = asyncio.run(ingest(src, IngestConfig(output_path=out)))
    assert result.table.num_rows == 1000
    assert (out / "tickets.arrow").exists()
    assert (out / "index.faiss").exists()


def test_e2e_jira_1k(tmp_path: Path, monkeypatch) -> None:
    _patch_embedder(monkeypatch)
    src = tmp_path / "issues.json"
    lines = []
    for i in range(1000):
        lines.append(
            json.dumps(
                {
                    "key": f"J-{i}",
                    "fields": {
                        "summary": f"Summary {i}",
                        "description": f"Description {i} long enough for chunking",
                        "status": {"name": "Open"},
                        "created": "2026-01-01T10:00:00Z",
                        "labels": [f"tag{i%10}"],
                    },
                }
            )
        )
    src.write_text("\n".join(lines) + "\n", encoding="utf-8")
    out = tmp_path / "out"
    result = asyncio.run(ingest(src, IngestConfig(output_path=out)))
    assert result.table.num_rows == 1000
    assert (out / "run_summary.json").exists()


def test_sira_roundtrip(tmp_path: Path, monkeypatch) -> None:
    _patch_embedder(monkeypatch)
    src = pa.table(
        {
            "id": ["1", "2", "3"],
            "subject": ["Login", "Payment", "Search"],
            "description": [
                "Cannot sign in due to token mismatch and auth failure",
                "Payment page errors with gateway timeout details",
                "Search index misses products in catalog for query",
            ],
            "status": ["open", "open", "open"],
            "created_at": ["2026-01-01T10:00:00Z"] * 3,
            "tags": [["auth"], ["pay"], ["search"]],
        }
    )
    out_dir = tmp_path / "out"
    result = asyncio.run(ingest(src, IngestConfig(output_path=out_dir, source_type="zendesk")))

    import faiss
    import pyarrow.ipc as ipc
    import numpy as np

    table = ipc.open_file(out_dir / "tickets.arrow").read_all()
    index = faiss.read_index(str(out_dir / "index.faiss"))
    q = np.array([[10.0, 11.0, 12.0]], dtype=np.float32)
    _d, ids = index.search(q, 1)
    picked = table.take([int(ids[0][0])])
    assert picked.num_rows == 1
    assert result.index.ntotal == table.num_rows


def test_benchmark_output_format(tmp_path: Path, monkeypatch) -> None:
    from click.testing import CliRunner

    monkeypatch.setattr(
        "kb_ingestor.cli.run_benchmark",
        lambda *_args, **_kwargs: [{"rows": 1000, "baseline_s": 2.2, "arrow_s": 1.0, "speedup_x": 2.2}],
    )
    src = tmp_path / "tickets.csv"
    src.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    out = tmp_path / "bench"
    runner = CliRunner()
    res = runner.invoke(cli, ["benchmark", "--source", str(src), "--rows", "1000", "--runs", "1", "--out", str(out)])
    assert res.exit_code == 0
    assert "| rows | baseline_s | arrow_s | speedup_x |" in res.output
    data = json.loads((out / "benchmark_results.json").read_text(encoding="utf-8"))
    assert data[0]["speedup_x"] >= 2.0
