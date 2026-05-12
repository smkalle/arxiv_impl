import asyncio
import importlib
import json
from pathlib import Path

import pyarrow as pa

from kb_ingestor.models import IngestConfig


api_module = importlib.import_module("kb_ingestor.api")


class FakeEmbedder:
    def encode(self, chunks, convert_to_numpy=True, batch_size=128):
        out = []
        for text in chunks:
            base = float(len(text))
            out.append([base, base + 1.0, base + 2.0])
        return out


def _write_csv_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "tickets.csv"
    path.write_text(
        "id,subject,description,status,created_at,tags\n"
        "1,Login issue,Cannot sign in,open,2026-01-01T10:00:00Z,auth\n"
        "2,Page error,Dashboard crashes,open,2026-01-02T10:00:00Z,web\n",
        encoding="utf-8",
    )
    return path


def _write_jira_fixture(tmp_path: Path) -> Path:
    path = tmp_path / "issues.json"
    path.write_text(
        '{"key":"J-1","fields":{"summary":"Login fail","description":"Cannot authenticate","status":{"name":"Open"},"created":"2026-01-01T10:00:00Z","labels":["auth"]}}\n'
        '{"key":"J-2","fields":{"summary":"UI bug","description":"Button overlap","status":{"name":"Done"},"created":"2026-01-02T11:00:00Z","labels":["ui"]}}\n',
        encoding="utf-8",
    )
    return path


def _patch_fake_embedder(monkeypatch) -> None:
    embed_module = importlib.import_module("kb_ingestor.ops.embed")
    monkeypatch.setattr(embed_module, "_load_embedder", lambda _name: FakeEmbedder())


def test_ingest_e2e_csv_source(tmp_path: Path, monkeypatch) -> None:
    _patch_fake_embedder(monkeypatch)
    csv_path = _write_csv_fixture(tmp_path)
    out_dir = tmp_path / "out"

    result = asyncio.run(api_module.ingest(csv_path, IngestConfig(output_path=out_dir)))
    assert result.table is not None
    assert "chunk" in result.table.column_names
    assert "embedding" in result.table.column_names
    assert "faiss_id" in result.table.column_names
    assert result.table.num_rows > 0
    assert result.index is not None
    assert result.index.ntotal == result.table.num_rows


def test_ingest_e2e_json_source(tmp_path: Path, monkeypatch) -> None:
    _patch_fake_embedder(monkeypatch)
    json_path = _write_jira_fixture(tmp_path)
    out_dir = tmp_path / "out"

    result = asyncio.run(api_module.ingest(json_path, IngestConfig(output_path=out_dir)))
    assert result.table is not None
    assert "chunk" in result.table.column_names
    assert "embedding" in result.table.column_names
    assert "faiss_id" in result.table.column_names
    assert result.index.ntotal == result.table.num_rows


def test_ingest_in_memory_no_artifacts(monkeypatch) -> None:
    _patch_fake_embedder(monkeypatch)
    source = pa.table(
        {
            "id": ["1"],
            "subject": ["Sub"],
            "description": ["Desc enough chars for chunking"],
            "status": ["open"],
            "created_at": ["2026-01-01T10:00:00Z"],
            "tags": [["a"]],
        }
    )
    result = asyncio.run(api_module.ingest(source, IngestConfig(output_path=None, source_type="zendesk")))
    assert result.table is not None
    assert result.index is not None
    assert result.artifacts == {}


def test_ingest_writes_required_artifacts(tmp_path: Path, monkeypatch) -> None:
    _patch_fake_embedder(monkeypatch)
    csv_path = _write_csv_fixture(tmp_path)
    out_dir = tmp_path / "out"

    asyncio.run(api_module.ingest(csv_path, IngestConfig(output_path=out_dir)))
    assert (out_dir / "tickets.arrow").exists()
    assert (out_dir / "index.faiss").exists()
    assert (out_dir / "run_summary.json").exists()


def test_run_summary_contains_embed_dim(tmp_path: Path, monkeypatch) -> None:
    _patch_fake_embedder(monkeypatch)
    csv_path = _write_csv_fixture(tmp_path)
    out_dir = tmp_path / "out"

    asyncio.run(api_module.ingest(csv_path, IngestConfig(output_path=out_dir)))
    summary = json.loads((out_dir / "run_summary.json").read_text(encoding="utf-8"))
    assert "embed_dim" in summary
    assert int(summary["embed_dim"]) > 0


def test_artifacts_reloadable(tmp_path: Path, monkeypatch) -> None:
    _patch_fake_embedder(monkeypatch)
    csv_path = _write_csv_fixture(tmp_path)
    out_dir = tmp_path / "out"

    result = asyncio.run(api_module.ingest(csv_path, IngestConfig(output_path=out_dir)))

    import pyarrow.ipc as ipc

    table = ipc.open_file(out_dir / "tickets.arrow").read_all()
    assert table.num_rows == result.table.num_rows

    import faiss

    index = faiss.read_index(str(out_dir / "index.faiss"))
    assert index.ntotal == result.table.num_rows
