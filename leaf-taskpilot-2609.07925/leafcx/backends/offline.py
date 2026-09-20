"""Backends that need no model at all.

`gold` replays the scenario's reference solution *through the real tool calls*,
which is what makes the whole harness testable in CI and on a phone with no
weights loaded: if a `gold` episode does not earn reward 1, the bug is in the
harness, not in the policy.  `noop` stops immediately and is the reward floor.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path
from typing import Any

from ..scenarios import TaskInstance, get as get_scenario
from .base import AssistantMessage, ToolCall


class NoopBackend:
    """Answers confidently, changes nothing. The zero-reward baseline."""

    name = "noop"

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        return AssistantMessage(
            content="I have reviewed the account and everything looks fine to me.",
            tool_calls=[],
        )


class GoldBackend:
    """Replays the reference solution as a sequence of real tool calls.

    The plan is derived, not hard-coded: the scenario's `solve()` runs against a
    throwaway copy of the workspace, and whichever account files it changed
    become `write` calls.  New scenarios therefore get a gold agent for free.
    """

    name = "gold"

    def __init__(self, task: TaskInstance, workspace: Path) -> None:
        self.task = task
        self.workspace = Path(workspace)
        self._plan: list[list[ToolCall]] | None = None
        self._step = 0

    def _build_plan(self) -> list[list[ToolCall]]:
        scratch = Path(tempfile.mkdtemp(prefix="leafcx-gold-"))
        mirror = scratch / "workspace"
        try:
            shutil.copytree(self.workspace, mirror)
            get_scenario(self.task.family).solve(self.task, mirror)
            writes: list[ToolCall] = []
            for after in sorted((mirror / "account").glob("*.json")):
                relative = f"account/{after.name}"
                before = self.workspace / relative
                new_text = after.read_text()
                if before.exists() and before.read_text() == new_text:
                    continue
                writes.append(ToolCall(name="write", arguments={"path": relative, "content": new_text}))
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

        # One tool call per turn, which is what the paper's trained checkpoints
        # converge to (~98% single-tool turns).
        plan: list[list[ToolCall]] = [
            [ToolCall(name="read", arguments={"path": "CUSTOMER_REQUEST.md"})],
            [ToolCall(name="glob", arguments={"pattern": "account/*.json"})],
        ]
        plan += [[call] for call in writes]
        plan.append([ToolCall(name="validate_account", arguments={})])
        plan.append([ToolCall(name="bash", arguments={"command": "python3 -m pytest -q tests/"})])
        return plan

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        if self._plan is None:
            self._plan = self._build_plan()
        if self._step >= len(self._plan):
            return AssistantMessage(
                content=(
                    "Done. I applied the reference solution for "
                    f"{self.task.family}, validated the account against the written "
                    "policies and ran the visible checks."
                ),
                tool_calls=[],
            )
        calls = self._plan[self._step]
        self._step += 1
        return AssistantMessage(content="", tool_calls=calls)


class ScriptedBackend:
    """Replays a fixed list of turns. Used by the harness's own tests."""

    name = "scripted"

    def __init__(self, turns: list[AssistantMessage]) -> None:
        self.turns = list(turns)
        self._step = 0

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> AssistantMessage:
        if self._step >= len(self.turns):
            return AssistantMessage(content="(script exhausted)", tool_calls=[])
        turn = self.turns[self._step]
        self._step += 1
        return turn
