from collections import Counter

import pytest

from src.df_filter import validate_sketch_terms


def test_rejects_df_zero():
    df_counter = Counter({"apple": 5, "banana": 3})
    result = validate_sketch_terms(["cherry"], df_counter, N=100, tau=0.01)
    assert result["validated"] == []
    assert result["rejected"] == ["cherry"]
    assert result["rejected_reasons"] == [{"term": "cherry", "reason": "df=0"}]


def test_rejects_too_common():
    df_counter = Counter({"error": 50, "account": 40})
    N = 100
    tau = 0.01
    result = validate_sketch_terms(["error"], df_counter, N, tau)
    assert result["validated"] == []
    assert result["rejected"] == ["error"]
    assert result["rejected_reasons"] == [{"term": "error", "reason": "too_common"}]


def test_keeps_valid_terms():
    df_counter = Counter({"rare_term": 1, "common_term": 50})
    N = 100
    tau = 0.01
    result = validate_sketch_terms(["rare_term"], df_counter, N, tau)
    assert result["validated"] == ["rare_term"]
    assert result["rejected"] == []


def test_case_insensitive():
    df_counter = Counter({"error": 50})
    N = 100
    tau = 0.01
    result = validate_sketch_terms(["ERROR"], df_counter, N, tau)
    assert result["validated"] == []
    assert result["rejected"] == ["error"]


def test_mixed_results():
    df_counter = Counter({"good": 1, "bad": 50, "missing": 0})
    N = 100
    tau = 0.01
    result = validate_sketch_terms(["good", "bad", "missing"], df_counter, N, tau)
    assert result["validated"] == ["good"]
    assert result["rejected"] == ["bad", "missing"]
    assert len(result["rejected_reasons"]) == 2
