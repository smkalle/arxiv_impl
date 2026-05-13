from __future__ import annotations

import json
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import pytest

from sira_kb_ingestor import IngestAndRetrieveConfig
from sira_kb_ingestor.errors import ArtifactBuildError
from sira_kb_ingestor.orchestration import setup_full_system


@dataclass
class _FakeTicketResult:
    metrics: dict = field(default_factory=lambda: {"rows_ingested": 2})
    artifacts: dict = field(default_factory=dict)
    table: object | None = None


async def _fake_ingest(ticket_source, config):
    print("[MOCK] Simulating AAFLOW ingest with artifact generation")
    out = Path(config.output_path)
    out.mkdir(parents=True, exist_ok=True)
    arrow = out / "tickets.arrow"
    index = out / "index.faiss"
    arrow.write_text("fake-arrow", encoding="utf-8")
    index.write_text("fake-faiss", encoding="utf-8")
    src_lines = Path(ticket_source).read_text(encoding="utf-8").splitlines()
    row_count = max(0, len(src_lines) - 1)
    return _FakeTicketResult(
        metrics={"rows_ingested": row_count},
        artifacts={"arrow_path": str(arrow), "faiss_path": str(index)},
    )


def _fake_enrich(kb_source, enriched_out, config):
    print("[MOCK] Simulating SIRA enrichment output")
    enriched_out.write_text('{"id":"kb-1","body":"x","enriched_terms":["a"]}\n', encoding="utf-8")
    return {"total": 1, "enriched": 1, "failed": 0, "skipped": 0}


def _fake_build(enriched_out, kb_index_path):
    print("[MOCK] Simulating SIRA BM25 index build")
    kb_index_path.write_text("fake-index", encoding="utf-8")

    class _Idx:
        articles = [{"id": "kb-1"}]

    return _Idx()


async def _fake_ingest_missing_artifacts(ticket_source, config):
    return _FakeTicketResult(metrics={"rows_ingested": 1}, artifacts={})


def test_setup_writes_summary(tmp_path: Path) -> None:
    print("[TEST] Validating setup_full_system writes setup_summary.json artifact")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n2,c,d\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n{"id":"kb-2","body":"billing"}\n', encoding="utf-8")

    out_dir = tmp_path / "out"
    cfg = IngestAndRetrieveConfig(output_path=out_dir)
    result = asyncio.run(
        setup_full_system(
            tickets,
            kb,
            cfg,
            ingest_fn=_fake_ingest,
            enrich_fn=_fake_enrich,
            build_index_fn=_fake_build,
        )
    )

    summary_path = Path(result.artifacts["setup_summary_path"])
    assert summary_path.exists()


def test_summary_schema_fields(tmp_path: Path) -> None:
    print("[TEST] Validating setup summary contains required schema fields")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")

    result = asyncio.run(
        setup_full_system(
            tickets,
            kb,
            IngestAndRetrieveConfig(output_path=tmp_path / "out"),
            ingest_fn=_fake_ingest,
            enrich_fn=_fake_enrich,
            build_index_fn=_fake_build,
        )
    )
    payload = json.loads(Path(result.artifacts["setup_summary_path"]).read_text(encoding="utf-8"))

    assert "timestamp" in payload
    assert payload["ticket_ingest"]["rows_ingested"] == 1
    assert payload["kb_enrichment"]["articles_enriched"] == 1
    assert "tau_default" in payload["retrieval"]


def test_missing_ticket_source_raises(tmp_path: Path) -> None:
    print("[TEST] Validating missing ticket source returns explicit file error")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        asyncio.run(
            setup_full_system(
                tmp_path / "missing.csv",
                kb,
                IngestAndRetrieveConfig(),
                ingest_fn=_fake_ingest,
                enrich_fn=_fake_enrich,
                build_index_fn=_fake_build,
            )
        )


def test_missing_kb_source_raises(tmp_path: Path) -> None:
    print("[TEST] Validating missing KB source returns explicit file error")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")

    with pytest.raises(FileNotFoundError):
        asyncio.run(
            setup_full_system(
                tickets,
                tmp_path / "missing.jsonl",
                IngestAndRetrieveConfig(),
                ingest_fn=_fake_ingest,
                enrich_fn=_fake_enrich,
                build_index_fn=_fake_build,
            )
        )


def test_result_shape_has_metrics_and_artifacts(tmp_path: Path) -> None:
    print("[TEST] Validating orchestration result exposes metrics and artifact contract")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")

    result = asyncio.run(
        setup_full_system(
            tickets,
            kb,
            IngestAndRetrieveConfig(output_path=tmp_path / "out"),
            ingest_fn=_fake_ingest,
            enrich_fn=_fake_enrich,
            build_index_fn=_fake_build,
        )
    )
    assert result.combined_metrics["elapsed_s"] >= 0
    assert "setup_summary_path" in result.artifacts
    assert Path(result.artifacts["ticket_index_path"]).exists()
    assert Path(result.artifacts["kb_index_path"]).exists()


def test_missing_required_ticket_artifact_raises(tmp_path: Path) -> None:
    print("[TEST] Validating setup fails when AAFLOW artifacts are missing")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")

    with pytest.raises(ArtifactBuildError, match="tickets.arrow"):
        asyncio.run(
            setup_full_system(
                tickets,
                kb,
                IngestAndRetrieveConfig(output_path=tmp_path / "out"),
                ingest_fn=_fake_ingest_missing_artifacts,
                enrich_fn=_fake_enrich,
                build_index_fn=_fake_build,
            )
        )


def test_missing_required_kb_artifact_raises(tmp_path: Path) -> None:
    print("[TEST] Validating setup fails when SIRA artifacts are missing")
    tickets = tmp_path / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    kb.write_text('{"id":"kb-1","body":"auth"}\n', encoding="utf-8")

    def fake_enrich_missing(kb_source, enriched_out, config):
        return {"total": 1, "enriched": 1, "failed": 0, "skipped": 0}

    with pytest.raises(ArtifactBuildError, match="enriched_kb.jsonl"):
        asyncio.run(
            setup_full_system(
                tickets,
                kb,
                IngestAndRetrieveConfig(output_path=tmp_path / "out"),
                ingest_fn=_fake_ingest,
                enrich_fn=fake_enrich_missing,
                build_index_fn=_fake_build,
            )
        )
