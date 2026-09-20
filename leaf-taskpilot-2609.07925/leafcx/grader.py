"""Hidden-test grading: the binary reward.

Reward is 1 if and only if every fail-to-pass and pass-to-pass test passes.  No
style score, no partial credit, no LLM judge — the same reward the paper uses,
and the reason a small model's improvement here is measurable at all.

The hidden tests live outside the workspace and the sandbox refuses to open
them, so the agent cannot read them, edit them, or make them pass by deleting
them.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import config
from .scenarios import TaskInstance, get as get_scenario

F2P_PREFIX = "test_f2p_"
P2P_PREFIX = "test_p2p_"


@dataclass
class TestOutcome:
    name: str
    passed: bool
    message: str = ""

    @property
    def kind(self) -> str:
        if self.name.startswith(F2P_PREFIX):
            return "f2p"
        if self.name.startswith(P2P_PREFIX):
            return "p2p"
        return "other"


@dataclass
class GradeResult:
    """Outcome of one grading pass."""

    reward: int
    outcomes: list[TestOutcome] = field(default_factory=list)
    error: str = ""

    @property
    def f2p(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if o.kind == "f2p"]

    @property
    def p2p(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if o.kind == "p2p"]

    @property
    def failures(self) -> list[TestOutcome]:
        return [o for o in self.outcomes if not o.passed]

    def summary(self) -> str:
        if self.error:
            return f"reward=0 (grader error: {self.error})"
        f2p_ok = sum(o.passed for o in self.f2p)
        p2p_ok = sum(o.passed for o in self.p2p)
        line = f"reward={self.reward} f2p={f2p_ok}/{len(self.f2p)} p2p={p2p_ok}/{len(self.p2p)}"
        if self.failures:
            line += "\n" + "\n".join(
                f"  FAIL {o.name}: {o.message.strip().splitlines()[-1][:160]}"
                for o in self.failures
                if o.message.strip()
            )
        return line

    def to_json(self) -> dict[str, Any]:
        return {
            "reward": self.reward,
            "error": self.error,
            "tests": [
                {"name": o.name, "kind": o.kind, "passed": o.passed, "message": o.message[:2000]}
                for o in self.outcomes
            ],
        }


def hidden_test_path(task: TaskInstance, hidden_dir: Path | None = None) -> Path:
    hidden_dir = Path(hidden_dir or config.HIDDEN_TESTS)
    return hidden_dir / f"test_{task.family}_{task.seed}_h{task.hint_level}.py"


def write_hidden_tests(task: TaskInstance, hidden_dir: Path | None = None) -> Path:
    """Materialise the generated hidden tests outside the workspace."""
    path = hidden_test_path(task, hidden_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(task.hidden_test_source)
    (path.parent / "task.json").write_text(json.dumps(task.to_json(), indent=2) + "\n")
    return path


def materialize(task: TaskInstance, workspace: Path | None = None, hidden_dir: Path | None = None) -> Path:
    """Reset the workspace to the task's starting state and emit its hidden tests."""
    workspace = Path(workspace or config.WORKSPACE)
    get_scenario(task.family).materialize(task, workspace)
    write_hidden_tests(task, hidden_dir)
    return workspace


def apply_gold(task: TaskInstance, workspace: Path | None = None) -> None:
    """Apply the scenario's gold solution to the current workspace."""
    get_scenario(task.family).solve(task, Path(workspace or config.WORKSPACE))


def grade(
    task: TaskInstance,
    workspace: Path | None = None,
    hidden_dir: Path | None = None,
    timeout: int = 180,
) -> GradeResult:
    """Run the hidden tests against the workspace's final state."""
    workspace = Path(workspace or config.WORKSPACE).resolve()
    tests = hidden_test_path(task, hidden_dir)
    if not tests.exists():
        tests = write_hidden_tests(task, hidden_dir)

    report = tests.parent / f"{tests.stem}.junit.xml"
    env = dict(os.environ)
    env["LEAFCX_WORKSPACE"] = str(workspace)
    # The hidden tests import leafcx; make sure they find this checkout even
    # when the package is not installed.
    env["PYTHONPATH"] = os.pathsep.join(
        [str(config.PROJECT_ROOT), env.get("PYTHONPATH", "")]
    ).rstrip(os.pathsep)

    try:
        subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                str(tests),
                "-q",
                "--tb=short",
                "-p",
                "no:cacheprovider",
                f"--junit-xml={report}",
            ],
            cwd=str(config.PROJECT_ROOT),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
    except subprocess.TimeoutExpired:
        return GradeResult(reward=0, error=f"hidden tests exceeded {timeout}s")

    if not report.exists():
        return GradeResult(reward=0, error="pytest produced no report (is pytest installed?)")

    outcomes = _parse_junit(report)
    report.unlink(missing_ok=True)
    if not outcomes:
        return GradeResult(reward=0, error="no hidden tests ran")
    reward = int(all(o.passed for o in outcomes))
    return GradeResult(reward=reward, outcomes=outcomes)


def _parse_junit(report: Path) -> list[TestOutcome]:
    try:
        root = ET.parse(report).getroot()
    except ET.ParseError:
        return []
    outcomes: list[TestOutcome] = []
    for case in root.iter("testcase"):
        name = case.get("name") or "?"
        problem = None
        for tag in ("failure", "error"):
            found = case.find(tag)
            if found is not None:
                problem = found
                break
        skipped = case.find("skipped") is not None
        if skipped:
            continue
        message = ""
        if problem is not None:
            message = (problem.get("message") or "") + "\n" + (problem.text or "")
        outcomes.append(TestOutcome(name=name, passed=problem is None, message=message))
    return outcomes


@dataclass
class TaskValidity:
    """Does this task behave like a task at all?

    The paper's tasks come with F2P tests that fail before the patch and P2P
    tests that pass throughout, plus a gold patch that turns everything green.
    A generated task that misses any of those is broken, and training on it
    teaches the policy nothing.
    """

    task_id: str
    f2p_fails_initially: bool
    p2p_passes_initially: bool
    gold_earns_reward: bool
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.f2p_fails_initially and self.p2p_passes_initially and self.gold_earns_reward


def validate_task(
    task: TaskInstance, workspace: Path | None = None, hidden_dir: Path | None = None
) -> TaskValidity:
    """Materialise, grade the empty start, apply gold, grade again."""
    workspace = Path(workspace or config.WORKSPACE)
    materialize(task, workspace, hidden_dir)
    before = grade(task, workspace, hidden_dir)

    details: list[str] = []
    f2p_fails = bool(before.f2p) and any(not o.passed for o in before.f2p)
    if not before.f2p:
        details.append("no fail-to-pass tests defined")
    elif not f2p_fails:
        details.append("every f2p test already passes on the starting state")

    p2p_passes = all(o.passed for o in before.p2p)
    if not p2p_passes:
        details.append(
            "p2p failing before any edit: "
            + "; ".join(o.name for o in before.p2p if not o.passed)
        )

    apply_gold(task, workspace)
    after = grade(task, workspace, hidden_dir)
    if after.reward != 1:
        details.append(
            "gold solution does not earn reward: "
            + "; ".join(f"{o.name}: {o.message.strip().splitlines()[-1][:120]}" for o in after.failures)
        )

    return TaskValidity(
        task_id=task.task_id,
        f2p_fails_initially=f2p_fails,
        p2p_passes_initially=p2p_passes,
        gold_earns_reward=after.reward == 1,
        detail="; ".join(details),
    )
