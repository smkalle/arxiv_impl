"""The Leaf loop: termination, budgets, error handling, metrics."""

from __future__ import annotations

import json
from pathlib import Path

from leafcx import agent, grader, scenarios
from leafcx.backends import AssistantMessage, ScriptedBackend, ToolCall
from leafcx.backends.base import BackendError
from leafcx.config import AgentConfig
from leafcx.usersim import ScriptedCustomer


def _task_and_workspace(workspace: Path, isolated_paths: Path, family: str = "shortlist_build"):
    task = scenarios.build(family, 3)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    return task


def _run(task, turns, workspace, **cfg_kwargs):
    cfg = AgentConfig(verbose=False, **cfg_kwargs)
    return agent.run_episode(task, cfg, backend=ScriptedBackend(turns), workspace=workspace)


def test_a_reply_with_no_tool_call_ends_the_episode(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(task, [AssistantMessage(content="All done.")], workspace)
    assert result.metrics.stopped_naturally
    assert result.metrics.steps == 1
    assert result.final_message == "All done."


def test_the_step_budget_is_enforced(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    looping = [
        AssistantMessage(tool_calls=[ToolCall(name="glob", arguments={"pattern": "*.json"})])
        for _ in range(10)
    ]
    result = _run(task, looping, workspace, max_steps=3)
    assert result.metrics.budget_exhausted
    assert not result.metrics.stopped_naturally
    assert result.metrics.steps == 3


def test_unknown_tools_are_reported_back_not_fatal(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(tool_calls=[ToolCall(name="delete_everything", arguments={})]),
            AssistantMessage(content="Understood."),
        ],
        workspace,
    )
    assert result.metrics.unknown_tools == 1
    assert result.metrics.stopped_naturally
    tool_message = [m for m in result.messages if m.get("role") == "tool"][0]
    assert "no tool named" in tool_message["content"]


def test_bad_arguments_are_reported_back(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(tool_calls=[ToolCall(name="read", arguments={"wrong": "arg"})]),
            AssistantMessage(content="ok"),
        ],
        workspace,
    )
    assert result.metrics.tool_errors == 1
    assert "bad arguments" in [m for m in result.messages if m.get("role") == "tool"][0]["content"]


def test_sandbox_violations_are_reported_back(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(
                tool_calls=[ToolCall(name="bash", arguments={"command": "curl http://evil"})]
            ),
            AssistantMessage(content="ok"),
        ],
        workspace,
    )
    content = [m for m in result.messages if m.get("role") == "tool"][0]["content"]
    assert content.startswith("blocked:")


def test_verification_before_stopping_is_measured(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    unverified = _run(
        task,
        [
            AssistantMessage(
                tool_calls=[ToolCall(name="write", arguments={"path": "notes.md", "content": "x"})]
            ),
            AssistantMessage(content="Done."),
        ],
        workspace,
    )
    assert not unverified.metrics.verified_before_stop

    verified = _run(
        task,
        [
            AssistantMessage(
                tool_calls=[ToolCall(name="write", arguments={"path": "notes.md", "content": "x"})]
            ),
            AssistantMessage(tool_calls=[ToolCall(name="validate_account", arguments={})]),
            AssistantMessage(content="Done."),
        ],
        workspace,
    )
    assert verified.metrics.verified_before_stop


def test_a_change_after_the_last_check_invalidates_it(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(tool_calls=[ToolCall(name="validate_account", arguments={})]),
            AssistantMessage(
                tool_calls=[ToolCall(name="write", arguments={"path": "notes.md", "content": "x"})]
            ),
            AssistantMessage(content="Done."),
        ],
        workspace,
    )
    assert not result.metrics.verified_before_stop


def test_running_pytest_counts_as_verification(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(
                tool_calls=[
                    ToolCall(name="bash", arguments={"command": "python3 -m pytest -q tests/"})
                ]
            ),
            AssistantMessage(content="Done."),
        ],
        workspace,
    )
    assert result.metrics.verified_before_stop


def test_single_tool_turn_rate(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(tool_calls=[ToolCall(name="glob", arguments={"pattern": "*.json"})]),
            AssistantMessage(
                tool_calls=[
                    ToolCall(name="glob", arguments={"pattern": "*.md"}),
                    ToolCall(name="glob", arguments={"pattern": "*.json"}),
                ]
            ),
            AssistantMessage(content="Done."),
        ],
        workspace,
    )
    assert result.metrics.turns_with_tools == 2
    assert result.metrics.single_tool_turn_rate == 0.5


def test_backend_errors_end_the_episode_cleanly(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)

    class Broken:
        name = "broken"

        def chat(self, messages, tools):
            raise BackendError("connection refused")

    result = agent.run_episode(task, AgentConfig(verbose=False), backend=Broken(), workspace=workspace)
    assert result.metrics.backend_error == "connection refused"
    assert not result.metrics.stopped_naturally


def test_the_customer_tool_appears_only_behind_the_flag(workspace: Path, isolated_paths: Path) -> None:
    from leafcx.tools import build_toolset

    without, schemas_without = build_toolset(None)
    assert "ask_customer" not in without
    assert all(s["function"]["name"] != "ask_customer" for s in schemas_without)

    with_sim, schemas_with = build_toolset(ScriptedCustomer({"budget": "under $20,000"}))
    assert "ask_customer" in with_sim
    assert any(s["function"]["name"] == "ask_customer" for s in schemas_with)


def test_the_simulated_customer_answers_from_its_facts(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(
        task,
        [
            AssistantMessage(
                tool_calls=[
                    ToolCall(name="ask_customer", arguments={"question": "What is your budget?"})
                ]
            ),
            AssistantMessage(content="Understood."),
        ],
        workspace,
        user_sim=True,
    )
    reply = [m for m in result.messages if m.get("role") == "tool"][0]["content"]
    assert "$" in reply


def test_transcripts_are_written_as_jsonl(workspace: Path, isolated_paths: Path) -> None:
    task = _task_and_workspace(workspace, isolated_paths)
    result = _run(task, [AssistantMessage(content="Done.")], workspace)
    path = agent.write_transcript(result, isolated_paths / "runs")
    lines = [json.loads(line) for line in path.read_text().splitlines()]
    assert lines[0]["record"] == "episode"
    assert lines[0]["task_id"] == task.task_id
    assert all(line["record"] in {"episode", "message"} for line in lines)
