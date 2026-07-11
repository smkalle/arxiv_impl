from __future__ import annotations

from src.evaluate import evaluate_rows, f1_at_k, hit_at_k, percentile


def test_metrics() -> None:
    assert hit_at_k(["A", "B"], ["B"]) == 1.0
    assert hit_at_k(["A"], ["B"]) == 0.0
    assert f1_at_k(["A", "B"], ["B"], k=2) == 1.0
    assert f1_at_k(["A", "B"], ["B", "C"], k=2) == 2 * (1 / 2) * (1 / 2) / ((1 / 2) + (1 / 2))
    assert percentile([1, 2, 3], 95) == 3


def test_evaluate_rows_reports_failures() -> None:
    rows = [{"ticket": "hello", "expected_kb_ids": ["KB-1"]}]
    report = evaluate_rows(rows, lambda _ticket: [{"id": "KB-2"}])

    assert report["count"] == 1
    assert report["hit_at_5"] == 0.0
    assert report["failures"][0]["expected_kb_ids"] == ["KB-1"]
