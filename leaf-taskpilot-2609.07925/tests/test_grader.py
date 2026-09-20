"""The reward has to mean something: gold wins, doing nothing loses."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from leafcx import grader, scenarios
from leafcx.config import AgentConfig
from leafcx.runner import run_task

SEEDS = (1, 2, 3)


@pytest.mark.parametrize("family", scenarios.FAMILIES)
@pytest.mark.parametrize("seed", SEEDS)
def test_generated_tasks_are_well_posed(
    family: str, seed: int, workspace: Path, isolated_paths: Path
) -> None:
    """F2P must fail before the work, P2P must pass throughout, gold must win."""
    task = scenarios.build(family, seed)
    validity = grader.validate_task(task, workspace, isolated_paths / "hidden_tests")
    assert validity.ok, validity.detail


@pytest.mark.parametrize("family", scenarios.FAMILIES)
def test_gold_backend_earns_the_reward(family: str) -> None:
    result = run_task(scenarios.build(family, 4), AgentConfig(backend="gold", verbose=False),
                      save_transcript=False)
    assert result.reward == 1, result.grade.summary()
    assert result.episode.metrics.verified_before_stop
    assert result.episode.metrics.stopped_naturally


@pytest.mark.parametrize("family", scenarios.FAMILIES)
def test_doing_nothing_earns_nothing(family: str) -> None:
    result = run_task(scenarios.build(family, 4), AgentConfig(backend="noop", verbose=False),
                      save_transcript=False)
    assert result.reward == 0
    assert not result.episode.metrics.verified_before_stop


def test_hidden_tests_live_outside_the_workspace(workspace: Path, isolated_paths: Path) -> None:
    task = scenarios.build("shortlist_build", 1)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    hidden = grader.hidden_test_path(task, isolated_paths / "hidden_tests")
    assert hidden.exists()
    assert workspace.resolve() not in hidden.resolve().parents
    assert not list(workspace.rglob("*hidden*"))


def test_grading_is_binary_across_all_tests(workspace: Path, isolated_paths: Path) -> None:
    task = scenarios.build("consent_prefs", 5)
    hidden = isolated_paths / "hidden_tests"
    grader.materialize(task, workspace, hidden)
    grader.apply_gold(task, workspace)
    assert grader.grade(task, workspace, hidden).reward == 1

    # Break exactly one pass-to-pass rule: grant marketing consent nobody asked for.
    path = workspace / "account" / "profile.json"
    profile = json.loads(path.read_text())
    profile["consents"]["marketing_email"] = True
    path.write_text(json.dumps(profile, indent=2))

    result = grader.grade(task, workspace, hidden)
    assert result.reward == 0
    assert any("marketing_email" in o.name or "marketing" in o.message for o in result.failures)


def test_partial_credit_does_not_exist(workspace: Path, isolated_paths: Path) -> None:
    task = scenarios.build("profile_update", 2)
    hidden = isolated_paths / "hidden_tests"
    grader.materialize(task, workspace, hidden)

    # Update the profile but leave the saved search and shortlist stale.
    path = workspace / "account" / "profile.json"
    profile = json.loads(path.read_text())
    profile["budget_max"] = task.params["new_budget"]
    path.write_text(json.dumps(profile, indent=2))

    result = grader.grade(task, workspace, hidden)
    assert result.reward == 0
    assert any(o.passed for o in result.f2p), "some progress was made"
    assert any(not o.passed for o in result.f2p), "but the task is not done"


def test_grade_summary_is_readable(workspace: Path, isolated_paths: Path) -> None:
    task = scenarios.build("shortlist_build", 1)
    hidden = isolated_paths / "hidden_tests"
    grader.materialize(task, workspace, hidden)
    summary = grader.grade(task, workspace, hidden).summary()
    assert "reward=0" in summary and "f2p=" in summary and "p2p=" in summary
