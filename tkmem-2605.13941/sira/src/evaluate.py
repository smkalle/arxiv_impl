"""Evaluation harness for baseline and TKMEM/EvolveMem-style retrieval."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.retrieve import evolved_retrieve, load_index, retrieve


def load_test_set(path: str | Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                row = json.loads(line)
                if "ticket" not in row or "expected_kb_ids" not in row:
                    raise ValueError("Each test row requires ticket and expected_kb_ids")
                rows.append(row)
    return rows


def hit_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int = 5) -> float:
    return 1.0 if set(retrieved_ids[:k]) & set(expected_ids) else 0.0


def f1_at_k(retrieved_ids: list[str], expected_ids: list[str], k: int = 5) -> float:
    if len(expected_ids) == 1:
        return hit_at_k(retrieved_ids, expected_ids, k=k)
    retrieved = set(retrieved_ids[:k])
    expected = set(expected_ids)
    if not retrieved or not expected:
        return 0.0
    true_positive = len(retrieved & expected)
    if true_positive == 0:
        return 0.0
    precision = true_positive / len(retrieved)
    recall = true_positive / len(expected)
    return 2 * precision * recall / (precision + recall)


def percentile(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, int(round((pct / 100) * (len(ordered) - 1))))
    return ordered[index]


def evaluate_rows(rows: list[dict[str, Any]], runner: Callable[[str], list[dict[str, Any]]]) -> dict[str, Any]:
    details: list[dict[str, Any]] = []
    latencies: list[float] = []
    for row in rows:
        start = time.perf_counter()
        results = runner(row["ticket"])
        latency_ms = (time.perf_counter() - start) * 1000
        latencies.append(latency_ms)
        retrieved_ids = [str(result["id"]) for result in results]
        expected = [str(item) for item in row["expected_kb_ids"]]
        details.append(
            {
                "ticket": row["ticket"],
                "expected_kb_ids": expected,
                "retrieved_ids": retrieved_ids,
                "hit_at_5": hit_at_k(retrieved_ids, expected),
                "f1_at_5": f1_at_k(retrieved_ids, expected),
                "latency_ms": latency_ms,
            }
        )
    return {
        "count": len(rows),
        "hit_at_5": statistics.mean(item["hit_at_5"] for item in details) if details else 0.0,
        "f1_at_5": statistics.mean(item["f1_at_5"] for item in details) if details else 0.0,
        "mean_latency_ms": statistics.mean(latencies) if latencies else 0.0,
        "p95_latency_ms": percentile(latencies, 95),
        "failures": [item for item in details if item["hit_at_5"] == 0.0],
        "details": details,
    }


def run_evaluation(test_set_path: str | Path, index_path: str | Path, report_path: str | Path) -> dict[str, Any]:
    load_index(index_path)
    rows = load_test_set(test_set_path)
    baseline = evaluate_rows(rows, lambda ticket: retrieve(ticket, top_k=5))
    evolved = evaluate_rows(rows, lambda ticket: evolved_retrieve(ticket, top_k=5)["results"])
    report = {
        "test_set": str(test_set_path),
        "index": str(index_path),
        "baseline": baseline,
        "evolved": evolved,
    }
    output = Path(report_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate baseline and TKMEM/EvolveMem-style retrieval.")
    parser.add_argument("--test-set", default="data/annotated_test_set.jsonl")
    parser.add_argument("--index", default="data/bm25_index.pkl")
    parser.add_argument("--report", default="data/eval_report.json")
    args = parser.parse_args()

    report = run_evaluation(args.test_set, args.index, args.report)
    print(f"count={report['baseline']['count']}")
    print(f"baseline_f1_at_5={report['baseline']['f1_at_5']:.3f}")
    print(f"evolved_f1_at_5={report['evolved']['f1_at_5']:.3f}")
    print(f"baseline_p95_latency_ms={report['baseline']['p95_latency_ms']:.2f}")
    print(f"evolved_p95_latency_ms={report['evolved']['p95_latency_ms']:.2f}")
    print(f"report={args.report}")


if __name__ == "__main__":
    main()
