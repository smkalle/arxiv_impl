"""Tests for DevSetEvaluator and build_dev_set."""
import csv
import json
import pytest
from dev_set import DevSetConfig, DevSetEvaluator, build_dev_set
from loops.action_space import RetrievalConfig


def test_build_dev_set(tmp_data):
    # Create minimal resolved_tickets.csv
    csv_path = tmp_data / "raw" / "resolved_tickets.csv"
    rows = [
        {"ticket_id": f"T-{i}", "ticket_text": f"problem {i}", "ground_truth_kb_id": f"KB-{i}", "product_area": "auth", "csat_score": 5}
        for i in range(10)
    ]
    with open(csv_path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)

    cfg = DevSetConfig(n_train=6, n_test=2, min_csat=4)
    train, test = build_dev_set(csv_path, tmp_data / "dev_set.json", tmp_data / "test_set.json", cfg)
    assert len(train) == 6
    assert len(test) == 2
    assert (tmp_data / "dev_set.json").exists()


def test_f1_perfect_retrieval(stub_router, sample_dev_set):
    from dev_set import DevSetEvaluator, DevSetConfig
    ev = DevSetEvaluator(sample_dev_set, DevSetConfig())
    ev.sample()
    # F1 should be > 0 since stub has relevant articles
    f1 = ev.compute_f1(stub_router, RetrievalConfig())
    assert 0.0 <= f1 <= 1.0


def test_f1_with_empty_corpus(sample_dev_set, tmp_data):
    from simplemem_router_stub import StubSimpleMemRouter
    empty = StubSimpleMemRouter().create("text")
    empty.finalize()
    ev = DevSetEvaluator(sample_dev_set)
    ev.sample()
    f1 = ev.compute_f1(empty, RetrievalConfig())
    assert f1 == 0.0
