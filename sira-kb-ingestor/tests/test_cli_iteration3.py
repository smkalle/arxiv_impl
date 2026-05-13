from __future__ import annotations

from click.testing import CliRunner

import sira_kb_ingestor.cli as cli_module
from sira_kb_ingestor.cli import cli


class _FakeRetriever:
    def __init__(self, artifact_dir):
        self.artifact_dir = artifact_dir

    def retrieve(self, text: str, top_k: int, tau: float, weight: float) -> dict:
        return {
            "kb_articles": [{"id": "KB-1", "title": "Auth", "body": "Body", "score": 1.0}],
            "audit": {"fallback_used": False, "latency_ms": 1},
        }


def test_query_command_prints_json(monkeypatch) -> None:
    print("[TEST] Validating query CLI prints retrieval JSON")
    monkeypatch.setattr(cli_module, "Retriever", _FakeRetriever)
    runner = CliRunner()

    result = runner.invoke(cli, ["query", "--text", "login fails", "--top-k", "2"])

    assert result.exit_code == 0
    assert '"kb_articles"' in result.output
    assert '"KB-1"' in result.output


def test_server_command_invokes_runner(monkeypatch) -> None:
    print("[TEST] Validating server CLI passes host/port/workers/out to runner")
    calls = {}

    def fake_run_server(host, port, workers, artifact_dir):
        calls.update({"host": host, "port": port, "workers": workers, "artifact_dir": artifact_dir})

    monkeypatch.setattr(cli_module, "run_server", fake_run_server)
    runner = CliRunner()

    result = runner.invoke(cli, ["server", "--host", "127.0.0.1", "--port", "9000", "--workers", "2", "--out", "/tmp/artifacts"])

    assert result.exit_code == 0
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 9000
    assert calls["workers"] == 2
    assert str(calls["artifact_dir"]) == "/tmp/artifacts"
