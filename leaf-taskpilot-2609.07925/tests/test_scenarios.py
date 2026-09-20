"""Every family must produce well-posed, reproducible tasks."""

from __future__ import annotations

import ast
import json
from pathlib import Path

import pytest

from leafcx import constraints as C
from leafcx import grader, scenarios

SEEDS = (1, 2, 3, 4, 5)


@pytest.mark.parametrize("family", scenarios.FAMILIES)
def test_tasks_are_reproducible(family: str) -> None:
    first = scenarios.build(family, 42)
    second = scenarios.build(family, 42)
    assert first.brief == second.brief
    assert first.params == second.params
    assert first.hidden_test_source == second.hidden_test_source


@pytest.mark.parametrize("family", scenarios.FAMILIES)
def test_hidden_tests_are_valid_python(family: str) -> None:
    for seed in SEEDS:
        source = scenarios.build(family, seed).hidden_test_source
        ast.parse(source)
        assert "test_f2p_" in source, "every task needs at least one fail-to-pass test"
        assert "test_p2p_" in source, "every task needs at least one pass-to-pass test"


@pytest.mark.parametrize("family", scenarios.FAMILIES)
@pytest.mark.parametrize("hint", scenarios.HINT_LEVELS)
def test_hint_levels_only_add_guidance(family: str, hint: int) -> None:
    behavioural = scenarios.build(family, 9, 0)
    hinted = scenarios.build(family, 9, hint)
    assert hinted.params == behavioural.params, "a hint must not change the task, only the brief"
    assert len(hinted.brief) >= len(behavioural.brief)
    if hint >= 1:
        assert "## Where to work" in hinted.brief
    if hint >= 2:
        assert "## Suggested procedure" in hinted.brief


@pytest.mark.parametrize("family", scenarios.FAMILIES)
def test_materialized_workspace_is_complete(family: str, workspace: Path, isolated_paths: Path) -> None:
    task = scenarios.build(family, 3)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    assert (workspace / "CUSTOMER_REQUEST.md").read_text() == task.brief
    assert (workspace / "tests" / "test_visible.py").exists()
    assert json.loads((workspace / "inventory" / "vehicles.json").read_text())
    for page in ("financing.md", "shortlist.md", "booking.md", "privacy.md"):
        assert (workspace / "policies" / page).exists()
    for name in ("profile.json", "shortlist.json", "audit_log.json"):
        json.loads((workspace / "account" / name).read_text())


@pytest.mark.parametrize("family", scenarios.FAMILIES)
def test_visible_tests_pass_on_the_starting_state(
    family: str, workspace: Path, isolated_paths: Path
) -> None:
    """The agent is told to run these; they must not be red before it starts."""
    import subprocess
    import sys

    task = scenarios.build(family, 3)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/"],
        cwd=str(workspace),
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr


def test_shortlist_gold_answer_is_unambiguous() -> None:
    """No TCO tie at the cut line, or the "correct" ranking is unknowable."""
    from leafcx import tco
    from leafcx.scenarios import base

    for seed in range(1, 16):
        task = scenarios.build("shortlist_build", seed)
        inventory = base.build_inventory(seed)
        miles = task.params["annual_miles"]
        qualifying = [v for v in inventory if C.matches(v, task.params["constraints"])]
        qualifying.sort(key=lambda v: base.rank_key(v, miles))
        size = task.params["shortlist_size"]
        assert [v["vin"] for v in qualifying[:size]] == task.params["expected_vins"]
        if len(qualifying) > size:
            assert tco.tco_5yr(qualifying[size], annual_miles=miles) > tco.tco_5yr(
                qualifying[size - 1], annual_miles=miles
            )


def test_shortlist_brief_states_every_hard_constraint() -> None:
    task = scenarios.build("shortlist_build", 6)
    brief = task.brief.lower()
    for fragment in C.describe(task.params["constraints"]):
        # Numbers are formatted with separators in the brief; compare on words.
        head = fragment.split(" ")[0].lower()
        assert head in brief


def test_consent_task_starts_with_something_to_revoke(workspace: Path, isolated_paths: Path) -> None:
    task = scenarios.build("consent_prefs", 2)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    profile = json.loads((workspace / "account" / "profile.json").read_text())
    assert profile["consents"]["data_sharing_partners"] is True
    assert profile["notifications"]["price_drop_sms"] is True
    assert profile["consents"]["marketing_email"] is False


def test_test_drive_starts_at_the_appointment_ceiling(workspace: Path, isolated_paths: Path) -> None:
    from leafcx import policy

    task = scenarios.build("test_drive", 2)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    appointments = json.loads((workspace / "account" / "appointments.json").read_text())
    booked = [a for a in appointments["appointments"] if a["status"] == "booked"]
    assert len(booked) == policy.MAX_OPEN_APPOINTMENTS, (
        "something must be cancelled before anything can be booked"
    )


def test_finance_family_generates_both_outcomes() -> None:
    outcomes = {
        scenarios.build("finance_prequal", seed).params["expected"]["status"]
        for seed in range(1, 9)
    }
    assert outcomes == {"prequalified", "referred"}


def test_unknown_family_is_rejected() -> None:
    with pytest.raises(KeyError):
        scenarios.get("no_such_family")
