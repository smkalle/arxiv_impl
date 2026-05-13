from __future__ import annotations

import asyncio
import csv
import json
import time
from dataclasses import replace
from pathlib import Path
from typing import Any, Iterable

from sira_kb_ingestor.models import IngestAndRetrieveConfig
from sira_kb_ingestor.orchestration import setup_full_system


def parse_row_counts(value: str | Iterable[int]) -> list[int]:
    if isinstance(value, str):
        rows = [int(part.strip()) for part in value.split(",") if part.strip()]
    else:
        rows = [int(part) for part in value]
    if not rows or any(row <= 0 for row in rows):
        raise ValueError("rows must contain one or more positive integers")
    return rows


def _cycle(values: list[str], target: int) -> list[str]:
    if not values:
        return []
    return [values[i % len(values)] for i in range(target)]


def _prepare_csv(source: Path, target_rows: int, destination: Path) -> Path:
    with source.open("r", encoding="utf-8", newline="") as fh:
        reader = list(csv.reader(fh))
    if not reader:
        raise ValueError(f"Ticket CSV is empty: {source}")
    header, data_rows = reader[0], reader[1:]
    if not data_rows:
        raise ValueError(f"Ticket CSV has no data rows: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(header)
        writer.writerows(_cycle(data_rows, target_rows))
    return destination


def _prepare_json(source: Path, target_rows: int, destination: Path) -> Path:
    text = source.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Ticket JSON is empty: {source}")

    rows: list[Any]
    try:
        parsed = json.loads(text)
        rows = parsed if isinstance(parsed, list) else [parsed]
    except json.JSONDecodeError:
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]

    if not rows:
        raise ValueError(f"Ticket JSON has no data rows: {source}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        "\n".join(json.dumps(row) for row in _cycle(rows, target_rows)) + "\n",
        encoding="utf-8",
    )
    return destination


def prepare_ticket_source(source: Path, target_rows: int, destination: Path) -> Path:
    suffix = source.suffix.lower()
    if suffix == ".csv":
        return _prepare_csv(source, target_rows, destination.with_suffix(".csv"))
    if suffix in {".json", ".jsonl"}:
        return _prepare_json(source, target_rows, destination.with_suffix(".json"))
    raise ValueError(f"Unsupported ticket source extension for benchmark: {source.suffix}")


def format_markdown_table(results: list[dict[str, Any]]) -> str:
    lines = [
        "| rows | run | elapsed_s | rows_per_sec | artifact_dir |",
        "|---:|---:|---:|---:|---|",
    ]
    for item in results:
        lines.append(
            f"| {item['rows']} | {item['run']} | {item['elapsed_s']:.4f} | "
            f"{item['rows_per_sec']:.2f} | {item['artifact_dir']} |"
        )
    return "\n".join(lines) + "\n"


async def run_setup_benchmark(
    tickets: Path,
    kb: Path,
    rows: list[int],
    runs: int,
    out: Path,
    config: IngestAndRetrieveConfig,
) -> dict[str, Any]:
    if runs <= 0:
        raise ValueError("runs must be a positive integer")
    if not tickets.exists():
        raise FileNotFoundError(f"Ticket source not found: {tickets}")
    if not kb.exists():
        raise FileNotFoundError(f"KB source not found: {kb}")

    out.mkdir(parents=True, exist_ok=True)
    prepared_dir = out / "inputs"
    results: list[dict[str, Any]] = []

    for row_count in rows:
        for run_no in range(1, runs + 1):
            prepared = prepare_ticket_source(tickets, row_count, prepared_dir / f"tickets_{row_count}_{run_no}")
            artifact_dir = out / f"setup_rows_{row_count}_run_{run_no}"
            run_config = replace(config, output_path=artifact_dir)

            started = time.perf_counter()
            result = await setup_full_system(prepared, kb, run_config)
            elapsed = time.perf_counter() - started
            ingested = int(result.combined_metrics.get("rows_ingested", row_count))
            results.append(
                {
                    "rows": row_count,
                    "run": run_no,
                    "elapsed_s": round(elapsed, 4),
                    "rows_per_sec": round(ingested / elapsed, 4) if elapsed > 0 else 0.0,
                    "artifact_dir": str(artifact_dir),
                    "rows_ingested": ingested,
                }
            )

    report = {
        "tickets": str(tickets),
        "kb": str(kb),
        "runs": runs,
        "results": results,
    }
    (out / "benchmark_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    table = format_markdown_table(results)
    (out / "benchmark_table.md").write_text(table, encoding="utf-8")
    report["markdown_table"] = table
    return report


def run_setup_benchmark_sync(
    tickets: Path,
    kb: Path,
    rows: list[int],
    runs: int,
    out: Path,
    config: IngestAndRetrieveConfig,
) -> dict[str, Any]:
    return asyncio.run(run_setup_benchmark(tickets=tickets, kb=kb, rows=rows, runs=runs, out=out, config=config))
