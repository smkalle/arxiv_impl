import pytest

from src.eval import compute_metrics, ndcg_at_k


def test_compute_metrics_perfect_ranking_ndcg10_is_one():
    qrels = {
        "T1": {
            "relevant_article_ids": ["KB-1", "KB-2"],
        }
    }
    results = {
        "T1": ["KB-1", "KB-2", "KB-3", "KB-4"],
    }
    metrics = compute_metrics(results, qrels)
    assert metrics["ndcg@10"] == 1.0


def test_compute_metrics_no_relevant_returned_recall5_zero():
    qrels = {
        "T1": {
            "relevant_article_ids": ["KB-9"],
        }
    }
    results = {
        "T1": ["KB-1", "KB-2", "KB-3", "KB-4", "KB-5"],
    }
    metrics = compute_metrics(results, qrels)
    assert metrics["recall@5"] == 0.0


def test_ndcg_known_value_matches_hand_calculation():
    gains = {"A": 3.0, "B": 2.0, "C": 1.0}
    ranked = ["B", "A", "C"]
    value = ndcg_at_k(ranked, gains, 3)
    # Hand-calculated expected value ~= 0.9225
    assert value == pytest.approx(0.9225, abs=0.001)


def test_compute_metrics_mrr_from_first_hit_rank():
    qrels = {
        "T1": {"relevant_article_ids": ["KB-X"]},
        "T2": {"relevant_article_ids": ["KB-Y"]},
    }
    results = {
        "T1": ["KB-A", "KB-X", "KB-B"],  # RR = 1/2
        "T2": ["KB-Y", "KB-C", "KB-D"],  # RR = 1
    }
    metrics = compute_metrics(results, qrels)
    assert metrics["mrr"] == 0.75


def test_compute_metrics_skips_empty_qrel_rows():
    qrels = {
        "T1": {"relevant_article_ids": ["KB-1"]},
        "T2": {"relevant_article_ids": []},
    }
    results = {
        "T1": ["KB-1"],
        "T2": ["KB-9"],
    }
    metrics = compute_metrics(results, qrels)
    assert metrics["num_queries"] == 1
