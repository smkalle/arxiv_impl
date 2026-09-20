"""The Leaf episode loop.

Structurally identical to the paper's harness: a system prompt, the customer's
request as the user turn, tool calls appended to the transcript with their
results, and termination when the model replies without calling a tool.

The metrics collected here are the ones the paper reports moving under RL —
single-tool-per-turn rate (~98% in late checkpoints) and the share of episodes
that verify before stopping (53.4% -> 94.3%).  A local run cannot reproduce
those numbers, but it can measure the same things, which is what makes the
harness worth having.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from . import config as config_mod
from .backends import AssistantMessage, Backend, BackendError, make_backend
from .config import AgentConfig
from .sandbox import SandboxError
from .scenarios import TaskInstance
from .tools import build_toolset
from .usersim import make_customer

SYSTEM_PROMPT = """You are the self-serve account assistant for a used-car marketplace.

You work on one customer's account. The account is a set of JSON files under
`account/`; the lot is `inventory/vehicles.json`; the rules you must follow are
written in `policies/`. Read the relevant policy page before you change the
thing it governs — the policies are binding and they are graded.

Your tools are `read`, `write`, `edit`, `glob` and `bash`, plus
`search_inventory`, `quote_finance` and `validate_account`.

How to work:
- Investigate before you act. Look at what is actually in the files.
- Make the smallest change that satisfies the request. Do not rewrite files you
  were not asked to touch.
- Prefer `edit` over `write` when you are changing part of a file.
- Never compute loan payments or cost of ownership yourself. `quote_finance` and
  `search_inventory` give you those numbers; copy them.
- Do what the customer asked for, not what you think they would enjoy. Granting
  a permission they did not ask for is a failure, not a bonus.
- Before you stop, call `validate_account` and run `python3 -m pytest -q tests/`.
  Fix whatever they report, then check again.

When the work is done and verified, reply with a short summary and call no tools.
That empty reply is how you end the episode."""


@dataclass
class EpisodeMetrics:
    """Behavioural statistics for one episode."""

    steps: int = 0
    tool_calls: int = 0
    calls_by_tool: dict[str, int] = field(default_factory=dict)
    tool_errors: int = 0
    unknown_tools: int = 0
    edit_failures: int = 0
    turns_with_tools: int = 0
    single_tool_turns: int = 0
    verified_before_stop: bool = False
    stopped_naturally: bool = False
    budget_exhausted: bool = False
    backend_error: str = ""
    wall_seconds: float = 0.0

    @property
    def single_tool_turn_rate(self) -> float:
        return self.single_tool_turns / self.turns_with_tools if self.turns_with_tools else 0.0

    def to_json(self) -> dict[str, Any]:
        return {
            **self.__dict__,
            "single_tool_turn_rate": round(self.single_tool_turn_rate, 4),
        }


@dataclass
class EpisodeResult:
    task_id: str
    family: str
    final_message: str
    messages: list[dict[str, Any]]
    metrics: EpisodeMetrics
    transcript_path: Path | None = None


#: Calls that count as the agent checking its own work.
VERIFICATION_TOOLS = {"validate_account"}
VERIFICATION_COMMANDS = ("pytest",)


def _is_verification(name: str, arguments: dict[str, Any]) -> bool:
    if name in VERIFICATION_TOOLS:
        return True
    if name == "bash":
        command = str(arguments.get("command", ""))
        return any(token in command for token in VERIFICATION_COMMANDS)
    return False


def run_episode(
    task: TaskInstance,
    cfg: AgentConfig | None = None,
    backend: Backend | None = None,
    workspace: Path | None = None,
    on_event: Callable[[str], None] | None = None,
) -> EpisodeResult:
    """Run one Leaf episode against an already-materialised workspace."""
    cfg = cfg or AgentConfig()
    workspace = Path(workspace or config_mod.WORKSPACE)
    backend = backend or make_backend(cfg, task=task, workspace=workspace)
    customer = make_customer(task, cfg)
    tools, schemas = build_toolset(customer)

    log = on_event or (lambda line: print(line) if cfg.verbose else None)

    messages: list[dict[str, Any]] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": task.brief},
    ]
    metrics = EpisodeMetrics()
    final_message = ""
    verified_since_last_change = False
    started = time.time()

    for step in range(1, cfg.max_steps + 1):
        metrics.steps = step
        try:
            reply: AssistantMessage = backend.chat(messages, schemas)
        except BackendError as exc:
            metrics.backend_error = str(exc)
            log(f"[step {step}] backend error: {exc}")
            break

        messages.append(_assistant_message(reply))

        if reply.is_final:
            final_message = reply.content
            metrics.stopped_naturally = True
            metrics.verified_before_stop = verified_since_last_change
            log(f"[step {step}] STOP\n{final_message.strip()[:1200]}")
            break

        metrics.turns_with_tools += 1
        if len(reply.tool_calls) == 1:
            metrics.single_tool_turns += 1

        for call in reply.tool_calls:
            metrics.tool_calls += 1
            metrics.calls_by_tool[call.name] = metrics.calls_by_tool.get(call.name, 0) + 1
            log(f"[step {step}] {call.name}({_short_args(call.arguments)})")

            if call.name not in tools:
                metrics.unknown_tools += 1
                result = (
                    f"error: no tool named {call.name!r}. "
                    f"Available: {', '.join(sorted(tools))}."
                )
            else:
                try:
                    result = str(tools[call.name](**call.arguments))
                except SandboxError as exc:
                    metrics.tool_errors += 1
                    result = f"blocked: {exc}"
                except TypeError as exc:
                    metrics.tool_errors += 1
                    result = f"tool error: bad arguments for {call.name}: {exc}"
                except Exception as exc:
                    metrics.tool_errors += 1
                    result = f"tool error: {type(exc).__name__}: {exc}"

            if call.name == "edit" and result.startswith("edit failed"):
                metrics.edit_failures += 1

            if _is_verification(call.name, call.arguments):
                verified_since_last_change = True
            elif call.name in {"write", "edit"}:
                # A change after the last check invalidates that check.
                verified_since_last_change = False

            messages.append(
                {
                    "role": "tool",
                    "tool_name": call.name,
                    "tool_call_id": call.call_id or call.name,
                    "content": result[: cfg.max_tool_chars],
                }
            )
    else:
        metrics.budget_exhausted = True
        final_message = "(step budget exhausted)"
        log(f"[step {cfg.max_steps}] budget exhausted")

    metrics.wall_seconds = round(time.time() - started, 2)
    if customer is not None:
        metrics.calls_by_tool.setdefault("ask_customer", 0)

    return EpisodeResult(
        task_id=task.task_id,
        family=task.family,
        final_message=final_message,
        messages=messages,
        metrics=metrics,
    )


def _assistant_message(reply: AssistantMessage) -> dict[str, Any]:
    message: dict[str, Any] = {"role": "assistant", "content": reply.content}
    if reply.tool_calls:
        message["tool_calls"] = [
            {
                "id": call.call_id or f"{call.name}-{index}",
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for index, call in enumerate(reply.tool_calls)
        ]
    return message


def _short_args(arguments: dict[str, Any], limit: int = 180) -> str:
    try:
        rendered = json.dumps(arguments)
    except (TypeError, ValueError):
        rendered = str(arguments)
    return rendered if len(rendered) <= limit else rendered[: limit - 3] + "..."


def write_transcript(result: EpisodeResult, runs_dir: Path | None = None) -> Path:
    """Append the episode to a JSONL run log. One line per message plus a header."""
    runs_dir = Path(runs_dir or config_mod.RUNS_DIR)
    runs_dir.mkdir(parents=True, exist_ok=True)
    path = runs_dir / f"{result.task_id}-{int(time.time())}.jsonl"
    with path.open("w") as handle:
        handle.write(
            json.dumps(
                {
                    "record": "episode",
                    "task_id": result.task_id,
                    "family": result.family,
                    "metrics": result.metrics.to_json(),
                    "final_message": result.final_message,
                }
            )
            + "\n"
        )
        for message in result.messages:
            handle.write(json.dumps({"record": "message", **message}) + "\n")
    result.transcript_path = path
    return path
