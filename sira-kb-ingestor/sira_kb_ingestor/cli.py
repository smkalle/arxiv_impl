from __future__ import annotations

import asyncio
import json
from pathlib import Path

import click

from sira_kb_ingestor.benchmark import parse_row_counts, run_setup_benchmark_sync
from sira_kb_ingestor.config import load_config
from sira_kb_ingestor.errors import ArtifactBuildError, EnrichmentError, RetrievalError, SiraIngestorError
from sira_kb_ingestor.orchestration import setup_full_system
from sira_kb_ingestor.retriever import Retriever
from sira_kb_ingestor.server import run_server


@click.group()
def cli() -> None:
    """sira-kb-ingestor command line interface."""


@cli.command("setup")
@click.option("--tickets", type=click.Path(path_type=Path), required=True, help="Zendesk CSV or Jira JSON ticket source.")
@click.option("--kb", type=click.Path(path_type=Path), required=True, help="SIRA KB JSONL source.")
@click.option("--out", "output_path", type=click.Path(path_type=Path), default=None, help="Output artifact directory.")
@click.option("--batch-size", type=int, default=None, help="Ticket embedding batch size.")
@click.option("--max-workers", type=int, default=None, help="Maximum ingest workers.")
@click.option("--embed-model", default=None, help="Sentence-transformers embedding model.")
@click.option("--enrichment-model", default=None, help="Ollama model used for KB enrichment.")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None, help="Optional TOML config path.")
def setup_cmd(
    tickets: Path,
    kb: Path,
    output_path: Path | None,
    batch_size: int | None,
    max_workers: int | None,
    embed_model: str | None,
    enrichment_model: str | None,
    config_path: Path | None,
) -> None:
    """Build ticket and KB retrieval artifacts."""
    cfg = load_config(
        config_path=config_path,
        cli_overrides={
            "output_path": output_path,
            "batch_size": batch_size,
            "max_workers": max_workers,
            "embed_model": embed_model,
            "enrichment_model": enrichment_model,
        },
    )
    try:
        result = asyncio.run(setup_full_system(tickets, kb, cfg))
    except FileNotFoundError as exc:
        raise click.ClickException(f"Missing input: {exc}") from exc
    except ArtifactBuildError as exc:
        raise click.ClickException(f"Artifact build failed: {exc}") from exc
    except EnrichmentError as exc:
        raise click.ClickException(f"Enrichment failed: {exc}") from exc
    except SiraIngestorError as exc:
        raise click.ClickException(f"Setup failed: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Setup runtime failed: {exc}") from exc

    summary = {
        "artifacts": result.artifacts,
        "rows_ingested": result.combined_metrics.get("rows_ingested", 0),
        "articles_enriched": result.kb_summary.get("enriched", 0),
        "elapsed_s": round(float(result.combined_metrics.get("elapsed_s", 0.0)), 4),
        "retrieval": {
            "top_k": cfg.top_k,
            "tau": cfg.tau,
            "weight": cfg.weight,
        },
    }
    click.echo(json.dumps(summary, indent=2))


@cli.command("query")
@click.option("--text", required=True, help="Ticket text to retrieve KB articles for.")
@click.option("--out", "artifact_dir", type=click.Path(path_type=Path), default=Path("./sira-artifacts"), show_default=True)
@click.option("--top-k", type=int, default=5, show_default=True)
@click.option("--tau", type=float, default=0.01, show_default=True)
@click.option("--weight", type=float, default=1.5, show_default=True)
def query_cmd(text: str, artifact_dir: Path, top_k: int, tau: float, weight: float) -> None:
    """Query KB retrieval artifacts."""
    try:
        response = Retriever(artifact_dir=artifact_dir).retrieve(text, top_k=top_k, tau=tau, weight=weight)
    except RetrievalError as exc:
        raise click.ClickException(f"Retrieval failed: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Unexpected query failure: {exc}") from exc
    click.echo(json.dumps(response, indent=2))


@cli.command("server")
@click.option("--out", "artifact_dir", type=click.Path(path_type=Path), default=Path("./sira-artifacts"), show_default=True)
@click.option("--host", default="0.0.0.0", show_default=True)
@click.option("--port", type=int, default=8000, show_default=True)
@click.option("--workers", type=int, default=4, show_default=True)
def server_cmd(artifact_dir: Path, host: str, port: int, workers: int) -> None:
    """Start the retrieval API server."""
    run_server(host=host, port=port, workers=workers, artifact_dir=artifact_dir)


@cli.command("benchmark")
@click.option("--tickets", type=click.Path(path_type=Path), required=True, help="Zendesk CSV or Jira JSON ticket source.")
@click.option("--kb", type=click.Path(path_type=Path), required=True, help="SIRA KB JSONL source.")
@click.option("--rows", default="1000,5000,10000", show_default=True, help="Comma-separated ticket row counts.")
@click.option("--runs", type=int, default=3, show_default=True, help="Runs per row count.")
@click.option("--out", "output_path", type=click.Path(path_type=Path), default=Path("./sira-artifacts/benchmarks"), show_default=True)
@click.option("--batch-size", type=int, default=None, help="Ticket embedding batch size.")
@click.option("--max-workers", type=int, default=None, help="Maximum ingest workers.")
@click.option("--embed-model", default=None, help="Sentence-transformers embedding model.")
@click.option("--enrichment-model", default=None, help="Ollama model used for KB enrichment.")
@click.option("--config", "config_path", type=click.Path(path_type=Path), default=None, help="Optional TOML config path.")
def benchmark_cmd(
    tickets: Path,
    kb: Path,
    rows: str,
    runs: int,
    output_path: Path,
    batch_size: int | None,
    max_workers: int | None,
    embed_model: str | None,
    enrichment_model: str | None,
    config_path: Path | None,
) -> None:
    """Measure setup throughput for ticket + KB artifact generation."""
    try:
        row_counts = parse_row_counts(rows)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc

    cfg = load_config(
        config_path=config_path,
        cli_overrides={
            "batch_size": batch_size,
            "max_workers": max_workers,
            "embed_model": embed_model,
            "enrichment_model": enrichment_model,
        },
    )
    try:
        report = run_setup_benchmark_sync(tickets=tickets, kb=kb, rows=row_counts, runs=runs, out=output_path, config=cfg)
    except FileNotFoundError as exc:
        raise click.ClickException(f"Missing input: {exc}") from exc
    except ArtifactBuildError as exc:
        raise click.ClickException(f"Artifact build failed: {exc}") from exc
    except EnrichmentError as exc:
        raise click.ClickException(f"Enrichment failed: {exc}") from exc
    except SiraIngestorError as exc:
        raise click.ClickException(f"Benchmark setup failed: {exc}") from exc
    except Exception as exc:
        raise click.ClickException(f"Benchmark runtime failed: {exc}") from exc
    click.echo(report["markdown_table"], nl=False)
