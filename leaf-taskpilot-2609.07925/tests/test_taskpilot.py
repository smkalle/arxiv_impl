"""The curriculum: admit near 0.5, refine the extremes, drop what cannot move."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leafcx import taskpilot
from leafcx.config import AgentConfig, TaskPilotConfig
from leafcx.scenarios import FAMILIES, HINT_LEVELS, build

BAND = (0.15, 0.65)


@pytest.mark.parametrize(
    "p_hat,hint,expected",
    [
        (0.50, 0, taskpilot.KEEP),
        (0.25, 1, taskpilot.KEEP),
        (0.00, 0, taskpilot.MAKE_EASIER),
        (0.10, 1, taskpilot.MAKE_EASIER),
        (0.00, max(HINT_LEVELS), taskpilot.DROP),
        (1.00, 2, taskpilot.MAKE_HARDER),
        (0.80, 1, taskpilot.MAKE_HARDER),
        (1.00, 0, taskpilot.DROP),
    ],
)
def test_classification_follows_the_learnability_frontier(p_hat, hint, expected) -> None:
    assert taskpilot.classify(p_hat, BAND, hint) == expected


def test_refinement_walks_the_hint_ladder() -> None:
    task = build("shortlist_build", 5, 0)
    easier = taskpilot.refine(task, taskpilot.MAKE_EASIER)
    assert easier is not None and easier.hint_level == 1
    assert easier.params == task.params, "refining changes the brief, not the task"

    hardest = build("shortlist_build", 5, max(HINT_LEVELS))
    assert taskpilot.refine(hardest, taskpilot.MAKE_EASIER) is None

    behavioural = build("shortlist_build", 5, 0)
    assert taskpilot.refine(behavioural, taskpilot.MAKE_HARDER) is None


def test_candidates_cycle_through_the_families() -> None:
    tasks = taskpilot.candidate_tasks(None, len(FAMILIES) * 2, seed_base=500)
    assert [t.family for t in tasks] == list(FAMILIES) * 2
    assert len({t.task_id for t in tasks}) == len(tasks)


def test_solve_rate_is_one_for_gold() -> None:
    cfg = AgentConfig(backend="gold", verbose=False)
    p_hat, rewards, stats = taskpilot.estimate_solve_rate(build("consent_prefs", 2), cfg, 3)
    assert p_hat == 1.0
    assert rewards == [1, 1, 1]
    assert stats["verified_before_stop"] == 1.0


def test_solve_rate_is_zero_for_a_policy_that_does_nothing() -> None:
    cfg = AgentConfig(backend="noop", verbose=False)
    p_hat, rewards, _ = taskpilot.estimate_solve_rate(build("consent_prefs", 2), cfg, 2)
    assert p_hat == 0.0
    assert rewards == [0, 0]


def test_a_policy_that_always_wins_gets_nothing_admitted() -> None:
    cfg = AgentConfig(backend="gold", verbose=False)
    tp = TaskPilotConfig(rollouts=1)
    report = taskpilot.run_iteration(1, [build("consent_prefs", 2, 0)], cfg, tp, BAND)
    assert report.admitted == []
    assert report.candidates[0].verdict == taskpilot.DROP
    assert report.summary()["solved_always"] == 1


def test_a_policy_that_always_fails_walks_the_ladder_then_stops() -> None:
    cfg = AgentConfig(backend="noop", verbose=False)
    tp = TaskPilotConfig(rollouts=1)
    report = taskpilot.run_iteration(1, [build("consent_prefs", 2, 0)], cfg, tp, BAND)
    assert report.admitted == []
    # Refined once within the pass, then left alone rather than looping.
    assert [c.hint_level for c in report.candidates] == [0, 1]
    assert report.candidates[0].verdict == taskpilot.MAKE_EASIER


def test_the_curriculum_writes_a_report_per_iteration(isolated_paths: Path) -> None:
    cfg = AgentConfig(backend="noop", verbose=False)
    tp = TaskPilotConfig(rollouts=1, iterations=2, candidates_per_iteration=2)
    tasks_dir = isolated_paths / "tasks"
    reports = taskpilot.run_curriculum(
        cfg, tp, families=["consent_prefs"], tasks_dir=tasks_dir, on_event=lambda line: None
    )
    assert len(reports) == 2
    for index in (1, 2):
        payload = json.loads((tasks_dir / f"iteration_{index}.json").read_text())
        assert payload["iteration"] == index
        assert payload["summary"]["candidates"] >= 2
    admitted = json.loads((tasks_dir / "admitted.json").read_text())
    assert admitted["tasks"] == []


def test_the_final_iteration_widens_the_band(isolated_paths: Path) -> None:
    cfg = AgentConfig(backend="noop", verbose=False)
    tp = TaskPilotConfig(rollouts=1, iterations=2, candidates_per_iteration=1)
    reports = taskpilot.run_curriculum(
        cfg, tp, families=["consent_prefs"], tasks_dir=isolated_paths / "tasks",
        on_event=lambda line: None,
    )
    assert reports[0].band == (tp.band_lo, tp.band_hi)
    assert reports[1].band == (tp.final_band_lo, tp.final_band_hi)
