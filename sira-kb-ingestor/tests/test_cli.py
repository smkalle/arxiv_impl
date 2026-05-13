from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from click.testing import CliRunner

import sira_kb_ingestor.cli as cli_module
from sira_kb_ingestor.cli import cli
from sira_kb_ingestor.errors import ArtifactBuildError, RetrievalError


@dataclass
class _FakeSetupResult:
    kb_summary: dict = field(default_factory=lambda: {"enriched": 2})
    combined_metrics: dict = field(default_factory=lambda: {"elapsed_s": 1.25, "rows_ingested": 3})
    artifacts: dict = field(default_factory=lambda: {"kb_index_path": "/tmp/out/kb_index.pkl"})


def test_setup_merges_config_calls_orchestration_and_prints_summary(monkeypatch, tmp_path: Path) -> None:
    print("[TEST] Validating setup CLI parses flags, merges config, and prints JSON summary")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")
    cfg_file = tmp_path / ".sira-ingest.toml"
    cfg_file.write_text("[ingest]\nbatch_size=10\nmax_workers=2\n", encoding="utf-8")
    calls = {}

    async def fake_setup(ticket_source, kb_source, config):
        calls.update({"tickets": ticket_source, "kb": kb_source, "config": config})
        return _FakeSetupResult()

    monkeypatch.setattr(cli_module, "setup_full_system", fake_setup)
    runner = CliRunner()

    result = runner.invoke(
        cli,
        [
            "setup",
            "--tickets",
            str(tickets),
            "--kb",
            str(kb),
            "--config",
            str(cfg_file),
            "--batch-size",
            "64",
            "--out",
            str(tmp_path / "out"),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows_ingested"] == 3
    assert payload["articles_enriched"] == 2
    assert payload["retrieval"] == {"top_k": 5, "tau": 0.01, "weight": 1.5}
    assert calls["tickets"] == tickets
    assert calls["kb"] == kb
    assert calls["config"].batch_size == 64
    assert calls["config"].max_workers == 2


def test_setup_missing_input_maps_to_click_error(monkeypatch, tmp_path: Path) -> None:
    print("[TEST] Validating setup CLI maps missing input to non-zero Click error")

    async def fake_setup(ticket_source, kb_source, config):
        raise FileNotFoundError("Ticket source not found: missing.csv")

    monkeypatch.setattr(cli_module, "setup_full_system", fake_setup)
    result = CliRunner().invoke(cli, ["setup", "--tickets", "missing.csv", "--kb", str(tmp_path / "kb.jsonl")])

    assert result.exit_code != 0
    assert "Missing input" in result.output


def test_setup_artifact_failure_maps_to_click_error(monkeypatch, tmp_path: Path) -> None:
    print("[TEST] Validating setup CLI maps artifact build failures")

    async def fake_setup(ticket_source, kb_source, config):
        raise ArtifactBuildError("Required artifact was not produced: kb_index.pkl")

    monkeypatch.setattr(cli_module, "setup_full_system", fake_setup)
    result = CliRunner().invoke(cli, ["setup", "--tickets", "tickets.csv", "--kb", "kb.jsonl"])

    assert result.exit_code != 0
    assert "Artifact build failed" in result.output


class _FailingRetriever:
    def __init__(self, artifact_dir):
        self.artifact_dir = artifact_dir

    def retrieve(self, text: str, top_k: int, tau: float, weight: float) -> dict:
        raise RetrievalError("KB index not found")


def test_query_exits_nonzero_on_retrieval_error(monkeypatch) -> None:
    print("[TEST] Validating query CLI exits non-zero on RetrievalError")
    monkeypatch.setattr(cli_module, "Retriever", _FailingRetriever)
    result = CliRunner().invoke(cli, ["query", "--text", "login fails"])

    assert result.exit_code != 0
    assert "Retrieval failed" in result.output


def test_server_defaults_match_spec(monkeypatch) -> None:
    print("[TEST] Validating server CLI defaults align to spec")
    calls = {}

    def fake_run_server(host, port, workers, artifact_dir):
        calls.update({"host": host, "port": port, "workers": workers, "artifact_dir": artifact_dir})

    monkeypatch.setattr(cli_module, "run_server", fake_run_server)
    result = CliRunner().invoke(cli, ["server"])

    assert result.exit_code == 0
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 8000
    assert calls["workers"] == 4


def test_benchmark_writes_reports_and_prints_markdown(monkeypatch, tmp_path: Path) -> None:
    print("[TEST] Validating benchmark CLI writes reports and prints Markdown table")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")
    out = tmp_path / "bench"

    def fake_benchmark(tickets, kb, rows, runs, out, config):
        out.mkdir(parents=True, exist_ok=True)
        table = "| rows | run | elapsed_s | rows_per_sec | artifact_dir |\n|---:|---:|---:|---:|---|\n| 2 | 1 | 0.1000 | 20.00 | /tmp/a |\n"
        (out / "benchmark_report.json").write_text(json.dumps({"results": [{"rows": 2}]}), encoding="utf-8")
        (out / "benchmark_table.md").write_text(table, encoding="utf-8")
        return {"markdown_table": table}

    monkeypatch.setattr(cli_module, "run_setup_benchmark_sync", fake_benchmark)
    result = CliRunner().invoke(
        cli,
        ["benchmark", "--tickets", str(tickets), "--kb", str(kb), "--rows", "2", "--runs", "1", "--out", str(out)],
    )

    assert result.exit_code == 0
    assert "| rows | run |" in result.output
    assert (out / "benchmark_report.json").exists()
    assert (out / "benchmark_table.md").exists()
