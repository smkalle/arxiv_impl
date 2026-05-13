from __future__ import annotations

import json
import os
import shutil
import sys
import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from sira_kb_ingestor.errors import ArtifactBuildError
from sira_kb_ingestor.models import IngestAndRetrieveConfig, IngestAndRetrieveResult


def normalize_ollama_host(host: str) -> str:
    if host.startswith(("http://", "https://")):
        return host
    return f"http://{host}"


def _count_ticket_rows(ticket_source: Path | Any) -> int:
    if hasattr(ticket_source, "num_rows"):
        return int(ticket_source.num_rows)
    path = Path(ticket_source)
    lines = path.read_text(encoding="utf-8").splitlines()
    if not lines:
        return 0
    suffix = path.suffix.lower()
    if suffix == ".csv":
        return max(0, len(lines) - 1)
    if suffix == ".json":
        return len(lines)
    return len(lines)


def _count_kb_articles(kb_source: Path) -> int:
    lines = kb_source.read_text(encoding="utf-8").splitlines()
    return len([ln for ln in lines if ln.strip()])


def _ensure_import_paths() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    aaflow_root = repo_root / "AAFLOW-2605.02162"
    sira_root = repo_root / "sira"
    if str(aaflow_root) not in sys.path:
        sys.path.insert(0, str(aaflow_root))
    if str(sira_root) not in sys.path:
        sys.path.insert(0, str(sira_root))


def _require_artifact(path: Path, label: str) -> None:
    if not path.exists():
        raise ArtifactBuildError(f"Required artifact was not produced: {label} ({path})")


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    tmp_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _default_ingest_fn(ticket_source: Path | Any, config: IngestAndRetrieveConfig):
    if config.embed_model == "deterministic-hash":
        from sira_kb_ingestor.deterministic_ingest import ingest_deterministic

        return ingest_deterministic(Path(ticket_source), config)

    _ensure_import_paths()
    from kb_ingestor.api import ingest
    from kb_ingestor.models import IngestConfig

    ingest_cfg = IngestConfig(
        batch_size=config.batch_size,
        max_workers=config.max_workers,
        embed_model=config.embed_model,
        max_chunk_chars=config.max_chunk_chars,
        min_chunk_chars=config.min_chunk_chars,
        output_path=config.output_path,
    )
    return ingest(ticket_source, ingest_cfg)


def _default_enrich_fn(kb_source: Path, enriched_out: Path, config: IngestAndRetrieveConfig) -> dict[str, Any]:
    _ensure_import_paths()
    import src.enrich as enrich_module

    enrich_module.OLLAMA_HOST = normalize_ollama_host(os.getenv("OLLAMA_HOST", config.ollama_host))
    return enrich_module.enrich_corpus(
        input_path=kb_source,
        output_path=enriched_out,
        model=config.enrichment_model,
    )


def _default_build_index_fn(enriched_out: Path, kb_index_path: Path) -> Any:
    _ensure_import_paths()
    from src.index import build_and_save

    return build_and_save(enriched_out, kb_index_path)


async def setup_full_system(
    ticket_source: Path | Any,
    kb_source: Path,
    config: IngestAndRetrieveConfig,
    ingest_fn: Callable[[Path | Any, IngestAndRetrieveConfig], Any] | None = None,
    enrich_fn: Callable[[Path, Path, IngestAndRetrieveConfig], dict[str, Any]] | None = None,
    build_index_fn: Callable[[Path, Path], Any] | None = None,
) -> IngestAndRetrieveResult:
    started = time.perf_counter()

    if isinstance(ticket_source, (str, Path)) and not Path(ticket_source).exists():
        raise FileNotFoundError(f"Ticket source not found: {ticket_source}")
    if not Path(kb_source).exists():
        raise FileNotFoundError(f"KB source not found: {kb_source}")

    ticket_rows = _count_ticket_rows(ticket_source)
    kb_rows = _count_kb_articles(Path(kb_source))

    out_dir = config.output_path or Path("./sira-artifacts")
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    tickets_arrow_path = out_dir / "tickets.arrow"
    ticket_index_path = out_dir / "ticket_index.faiss"
    enriched_kb_path = out_dir / "enriched_kb.jsonl"
    kb_index_path = out_dir / "kb_index.pkl"

    active_ingest_fn = ingest_fn or _default_ingest_fn
    active_enrich_fn = enrich_fn or _default_enrich_fn
    active_build_index_fn = build_index_fn or _default_build_index_fn

    ingest_started = time.perf_counter()
    ingest_config = replace(config, output_path=out_dir)
    ticket_result = await active_ingest_fn(ticket_source, ingest_config)
    ingest_elapsed = time.perf_counter() - ingest_started

    aaflow_arrow = Path(ticket_result.artifacts.get("arrow_path", tickets_arrow_path))
    aaflow_index = Path(ticket_result.artifacts.get("faiss_path", out_dir / "index.faiss"))
    if aaflow_arrow != tickets_arrow_path and aaflow_arrow.exists():
        shutil.copyfile(aaflow_arrow, tickets_arrow_path)
    if aaflow_index != ticket_index_path and aaflow_index.exists():
        shutil.copyfile(aaflow_index, ticket_index_path)
    _require_artifact(tickets_arrow_path, "tickets.arrow")
    _require_artifact(ticket_index_path, "ticket_index.faiss")

    enrich_started = time.perf_counter()
    kb_summary = active_enrich_fn(Path(kb_source), enriched_kb_path, config)
    _require_artifact(enriched_kb_path, "enriched_kb.jsonl")
    kb_index_obj = active_build_index_fn(enriched_kb_path, kb_index_path)
    _require_artifact(kb_index_path, "kb_index.pkl")
    enrich_elapsed = time.perf_counter() - enrich_started

    effective_ticket_rows = int(ticket_result.metrics.get("rows_ingested", ticket_rows)) if getattr(ticket_result, "metrics", None) else ticket_rows
    effective_embed_dim = 384
    if getattr(ticket_result, "table", None) is not None and ticket_result.table.num_rows > 0:
        first = ticket_result.table.column("embedding")[0].as_py()
        effective_embed_dim = len(first)

    summary = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "ticket_ingest": {
            "rows_ingested": effective_ticket_rows,
            "elapsed_s": round(ingest_elapsed, 4),
            "throughput_rps": round(effective_ticket_rows / ingest_elapsed, 4) if ingest_elapsed > 0 else 0.0,
            "embed_model": config.embed_model,
            "embed_dim": effective_embed_dim,
        },
        "kb_enrichment": {
            "articles_enriched": int(kb_summary.get("enriched", kb_rows)),
            "elapsed_s": round(enrich_elapsed, 4),
            "enrichment_model": config.enrichment_model,
            "failed": int(kb_summary.get("failed", 0)),
            "skipped": int(kb_summary.get("skipped", 0)),
        },
        "retrieval": {
            "tau_default": config.tau,
            "weight_default": config.weight,
        },
    }

    summary_path = out_dir / "setup_summary.json"
    _write_json_atomic(summary_path, summary)

    elapsed = time.perf_counter() - started
    result = IngestAndRetrieveResult(
        ticket_result=ticket_result,
        kb_summary=kb_summary,
        combined_metrics={
            "elapsed_s": elapsed,
            "rows_ingested": effective_ticket_rows,
            "ticket_ingest_elapsed_s": ingest_elapsed,
            "kb_enrichment_elapsed_s": enrich_elapsed,
            "kb_index_articles": len(getattr(kb_index_obj, "articles", [])),
        },
        artifacts={
            "setup_summary_path": str(summary_path),
            "tickets_arrow_path": str(tickets_arrow_path),
            "ticket_index_path": str(ticket_index_path),
            "enriched_kb_path": str(enriched_kb_path),
            "kb_index_path": str(kb_index_path),
        },
    )
    return result
