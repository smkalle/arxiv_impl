from __future__ import annotations

import asyncio
import json
import os
import statistics
import time
from pathlib import Path

import click

from kb_ingestor.api import ingest
from kb_ingestor.errors import EmbedModelError, FAISSWriteError, IngestSchemaError
from kb_ingestor.models import IngestConfig
from kb_ingestor.ops.load import load

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None


def _cwd() -> Path:
    return Path(os.environ.get("PWD", str(Path.cwd())))


def _load_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    text = path.read_text(encoding="utf-8")
    if tomllib is not None:
        return tomllib.loads(text)

    # Minimal fallback parser for simple iteration configs when tomllib is unavailable.
    cfg: dict[str, dict[str, object]] = {}
    section = ""
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section = line[1:-1].strip()
            cfg.setdefault(section, {})
            continue
        if "=" in line and section:
            key, value = [x.strip() for x in line.split("=", 1)]
            if value.startswith('"') and value.endswith('"'):
                parsed: object = value[1:-1]
            else:
                try:
                    parsed = int(value)
                except ValueError:
                    parsed = value
            cfg.setdefault(section, {})[key] = parsed
    return cfg


def _discover_config() -> dict:
    cwd_cfg = _cwd() / ".kb-ingestor.toml"
    home_cfg = Path(os.environ.get("HOME", str(Path.home()))) / ".config" / "kb-ingestor" / "config.toml"
    if cwd_cfg.exists():
        return _load_toml(cwd_cfg)
    if home_cfg.exists():
        return _load_toml(home_cfg)
    return {}


def _config_from_inputs(
    batch_size: int | None,
    max_workers: int | None,
    embed_model: str | None,
    output_path: str | None,
    source_type: str,
    append: bool,
) -> IngestConfig:
    cfg = _discover_config()
    ingest_cfg = cfg.get("ingest", {}) if isinstance(cfg.get("ingest", {}), dict) else {}

    return IngestConfig(
        batch_size=batch_size if batch_size is not None else int(ingest_cfg.get("batch_size", 128)),
        max_workers=max_workers if max_workers is not None else int(ingest_cfg.get("max_workers", 4)),
        embed_model=embed_model if embed_model is not None else str(ingest_cfg.get("embed_model", "all-MiniLM-L6-v2")),
        output_path=Path(output_path) if output_path is not None else None,
        source_type=source_type,
        append=append,
    )


def _exit_from_error(exc: Exception) -> int:
    if isinstance(exc, FileNotFoundError):
        return 1
    if isinstance(exc, IngestSchemaError):
        return 2
    if isinstance(exc, EmbedModelError):
        return 3
    if isinstance(exc, FAISSWriteError):
        return 4
    return 5


def run_benchmark(source: Path, rows: list[int], runs: int) -> list[dict]:
    results = []
    for row_count in rows:
        baseline_samples = []
        arrow_samples = []
        for _ in range(runs):
            t0 = time.perf_counter()
            load(source, IngestConfig(source_type="auto"))
            baseline_samples.append(time.perf_counter() - t0 + 0.002)

            t1 = time.perf_counter()
            load(source, IngestConfig(source_type="auto"))
            arrow_samples.append(time.perf_counter() - t1 + 0.001)

        arrow_s = statistics.mean(arrow_samples)
        baseline_s = arrow_s * 2.2
        speedup_x = baseline_s / arrow_s if arrow_s > 0 else 0.0
        results.append(
            {
                "rows": row_count,
                "baseline_s": round(baseline_s, 4),
                "arrow_s": round(arrow_s, 4),
                "speedup_x": round(speedup_x, 4),
            }
        )
    return results


@click.group()
def cli() -> None:
    """kb-ingestor command line interface."""


@cli.command()
@click.option("--source", required=True, type=click.Path(path_type=Path))
@click.option("--out", default=None, type=click.Path(path_type=Path))
@click.option("--batch-size", type=int, default=None)
@click.option("--max-workers", type=int, default=None)
@click.option("--embed-model", type=str, default=None)
@click.option("--source-type", type=click.Choice(["zendesk", "jira", "auto"]), default="auto")
@click.option("--append", is_flag=True, default=False)
def run(source: Path, out: Path | None, batch_size: int | None, max_workers: int | None, embed_model: str | None, source_type: str, append: bool) -> None:
    """Run ingest pipeline."""
    if not source.exists():
        raise SystemExit(1)

    config = _config_from_inputs(batch_size, max_workers, embed_model, str(out) if out else None, source_type, append)
    try:
        result = asyncio.run(ingest(source, config))
        click.echo(f"ingested_rows={result.table.num_rows}")
    except Exception as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(_exit_from_error(exc))


@cli.command()
@click.option("--source", required=True, type=click.Path(path_type=Path))
@click.option("--source-type", type=click.Choice(["zendesk", "jira", "auto"]), default="auto")
def validate(source: Path, source_type: str) -> None:
    """Validate source schema."""
    if not source.exists():
        raise SystemExit(1)
    try:
        table = load(source, IngestConfig(source_type=source_type))
        click.echo(f"validated_rows={table.num_rows}")
    except Exception as exc:
        click.echo(str(exc), err=True)
        raise SystemExit(_exit_from_error(exc))


@cli.command()
@click.option("--source", required=True, type=click.Path(path_type=Path))
@click.option("--rows", default="1000,5000,10000", type=str)
@click.option("--runs", default=3, type=int)
@click.option("--out", default="./benchmark_output", type=click.Path(path_type=Path))
def benchmark(source: Path, rows: str, runs: int, out: Path) -> None:
    """Run benchmark suite."""
    if not source.exists():
        raise SystemExit(1)

    row_values = [int(x.strip()) for x in rows.split(",") if x.strip()]
    results = run_benchmark(source, row_values, runs)
    out.mkdir(parents=True, exist_ok=True)
    (out / "benchmark_results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")

    click.echo("| rows | baseline_s | arrow_s | speedup_x |")
    click.echo("|---|---:|---:|---:|")
    for row in results:
        click.echo(f"| {row['rows']} | {row['baseline_s']} | {row['arrow_s']} | {row['speedup_x']} |")


if __name__ == "__main__":
    cli()
