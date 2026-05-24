"""Tests for MetaAnalyzer guard logic."""
import pytest
from loops.meta_analyzer import MetaAnalyzer


def test_accept_on_improvement():
    m = MetaAnalyzer()
    decision, reason = m.evaluate(0.40, 0.45)
    assert decision == "accept"
    assert reason is None


def test_revert_on_regression():
    m = MetaAnalyzer()
    decision, reason = m.evaluate(0.45, 0.40)
    assert decision == "revert"
    assert "regressed" in reason


def test_reject_on_no_improvement():
    m = MetaAnalyzer()
    decision, reason = m.evaluate(0.40, 0.40)
    assert decision == "reject"


def test_explore_after_plateau():
    m = MetaAnalyzer(plateau_patience=2)
    m.evaluate(0.40, 0.40)  # reject (flat_rounds=1)
    decision, reason = m.evaluate(0.40, 0.40)  # should trigger explore
    assert decision == "explore"
    assert "plateau" in reason


def test_flat_counter_resets_after_accept():
    m = MetaAnalyzer(plateau_patience=2)
    m.evaluate(0.40, 0.40)  # flat_rounds=1
    m.evaluate(0.40, 0.45)  # accept — resets counter
    # next flat shouldn't trigger explore immediately
    decision, _ = m.evaluate(0.45, 0.45)
    assert decision == "reject"  # flat_rounds=1, not yet explore


def test_stagnating_property():
    m = MetaAnalyzer(plateau_patience=2)
    assert not m.stagnating
    m.evaluate(0.40, 0.40)  # flat_rounds=1
    assert m.stagnating
