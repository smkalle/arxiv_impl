from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

import sira_kb_ingestor.benchmark as benchmark_module
from sira_kb_ingestor.benchmark import parse_row_counts, run_setup_benchmark
from sira_kb_ingestor.models import IngestAndRetrieveConfig


@dataclass
class _FakeSetupResult:
    combined_metrics: dict = field(default_factory=lambda: {"rows_ingested": 0})
    kb_summary: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)


def test_parse_row_counts() -> None:
    print("[TEST] Validating benchmark row count parser")
    assert parse_row_counts("10, 20,30") == [10, 20, 30]
    with pytest.raises(ValueError):
        parse_row_counts("0")


def test_run_setup_benchmark_writes_report_and_table(monkeypatch, tmp_path: Path) -> None:
    print("[TEST] Validating benchmark runner prepares inputs and writes report artifacts")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n2,c,d\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")
    calls = []

    async def fake_setup(ticket_source, kb_source, config):
        calls.append((Path(ticket_source), Path(kb_source), config.output_path))
        prepared_rows = max(0, len(Path(ticket_source).read_text(encoding="utf-8").splitlines()) - 1)
        return _FakeSetupResult(combined_metrics={"rows_ingested": prepared_rows})

    monkeypatch.setattr(benchmark_module, "setup_full_system", fake_setup)

    report = asyncio.run(
        run_setup_benchmark(
            tickets=tickets,
            kb=kb,
            rows=[3],
            runs=2,
            out=tmp_path / "bench",
            config=IngestAndRetrieveConfig(batch_size=8),
        )
    )

    assert len(report["results"]) == 2
    assert report["results"][0]["rows_ingested"] == 3
    assert "| rows | run |" in report["markdown_table"]
    assert (tmp_path / "bench" / "benchmark_report.json").exists()
    assert (tmp_path / "bench" / "benchmark_table.md").exists()
    assert calls[0][0].exists()
