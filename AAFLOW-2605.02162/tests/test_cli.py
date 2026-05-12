import json
from pathlib import Path

import pyarrow as pa
from click.testing import CliRunner

from kb_ingestor.errors import EmbedModelError, FAISSWriteError, IngestSchemaError
from kb_ingestor.models import IngestResult


def _write_csv(tmp_path: Path) -> Path:
    path = tmp_path / "tickets.csv"
    path.write_text(
        "id,subject,description,status,created_at,tags\n"
        "1,Login issue,Cannot sign in,open,2026-01-01T10:00:00Z,auth\n",
        encoding="utf-8",
    )
    return path


def test_cli_run_success_exit_0(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    async def fake_ingest(_source, _config):
        return IngestResult(table=pa.table({"id": ["1"]}), index=type("Idx", (), {"ntotal": 1})(), metrics={}, artifacts={})

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(cli, ["run", "--source", str(source), "--out", str(tmp_path / "out")])
    assert result.exit_code == 0


def test_cli_validate_success_exit_0(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    monkeypatch.setattr("kb_ingestor.cli.load", lambda *_args, **_kwargs: pa.table({"id": ["1"]}))
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(cli, ["validate", "--source", str(source)])
    assert result.exit_code == 0


def test_cli_benchmark_success_exit_0(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    def fake_bench(*_args, **_kwargs):
        return [{"rows": 1000, "baseline_s": 2.0, "arrow_s": 1.0, "speedup_x": 2.0}]

    monkeypatch.setattr("kb_ingestor.cli.run_benchmark", fake_bench)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    out = tmp_path / "bench_out"
    result = runner.invoke(cli, ["benchmark", "--source", str(source), "--rows", "1000", "--runs", "1", "--out", str(out)])
    assert result.exit_code == 0
    assert "| rows | baseline_s | arrow_s | speedup_x |" in result.output
    assert (out / "benchmark_results.json").exists()


def test_cli_run_input_not_found_exit_1(tmp_path: Path) -> None:
    from kb_ingestor.cli import cli

    runner = CliRunner()
    result = runner.invoke(cli, ["run", "--source", str(tmp_path / "missing.csv")])
    assert result.exit_code == 1


def test_cli_run_schema_failure_exit_2(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    async def fake_ingest(_source, _config):
        raise IngestSchemaError(["description"])

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(cli, ["run", "--source", str(source)])
    assert result.exit_code == 2


def test_cli_run_embed_failure_exit_3(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    async def fake_ingest(_source, _config):
        raise EmbedModelError("model", "boom")

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(cli, ["run", "--source", str(source)])
    assert result.exit_code == 3


def test_cli_run_faiss_write_failure_exit_4(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    async def fake_ingest(_source, _config):
        raise FAISSWriteError("/tmp/x", "disk full")

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(cli, ["run", "--source", str(source)])
    assert result.exit_code == 4


def test_cli_run_unexpected_error_exit_5(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    async def fake_ingest(_source, _config):
        raise RuntimeError("unexpected")

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(cli, ["run", "--source", str(source)])
    assert result.exit_code == 5


def test_cli_config_precedence_flags_override_file(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    cfg = tmp_path / ".kb-ingestor.toml"
    cfg.write_text("[ingest]\nbatch_size=11\n", encoding="utf-8")
    captured = {}

    async def fake_ingest(_source, config):
        captured["batch_size"] = config.batch_size
        return IngestResult(table=pa.table({"id": ["1"]}), index=type("Idx", (), {"ntotal": 1})(), metrics={}, artifacts={})

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(
        cli,
        ["run", "--source", str(source), "--batch-size", "7"],
        env={"PWD": str(tmp_path)},
    )
    assert result.exit_code == 0
    assert captured["batch_size"] == 7


def test_cli_config_discovery_order(tmp_path: Path, monkeypatch) -> None:
    from kb_ingestor.cli import cli

    cwd_cfg = tmp_path / ".kb-ingestor.toml"
    cwd_cfg.write_text("[ingest]\nbatch_size=13\n", encoding="utf-8")
    home = tmp_path / "home"
    user_cfg = home / ".config" / "kb-ingestor" / "config.toml"
    user_cfg.parent.mkdir(parents=True, exist_ok=True)
    user_cfg.write_text("[ingest]\nbatch_size=19\n", encoding="utf-8")
    captured = {}

    async def fake_ingest(_source, config):
        captured["batch_size"] = config.batch_size
        return IngestResult(table=pa.table({"id": ["1"]}), index=type("Idx", (), {"ntotal": 1})(), metrics={}, artifacts={})

    monkeypatch.setattr("kb_ingestor.cli.ingest", fake_ingest)
    runner = CliRunner()
    source = _write_csv(tmp_path)
    result = runner.invoke(
        cli,
        ["run", "--source", str(source)],
        env={"PWD": str(tmp_path), "HOME": str(home)},
    )
    assert result.exit_code == 0
    assert captured["batch_size"] == 13
