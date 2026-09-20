"""Command line: `python3 -m leafcx <command>`."""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

from . import config as config_mod
from . import grader, scenarios, taskpilot
from .backends import BACKEND_NAMES, BackendError, make_backend
from .config import AgentConfig, TaskPilotConfig
from .runner import run_task
from .scenarios import FAMILIES


def _agent_config(args: argparse.Namespace) -> AgentConfig:
    cfg = AgentConfig()
    for field in ("backend", "model", "base_url", "max_steps", "temperature"):
        value = getattr(args, field, None)
        if value is not None:
            setattr(cfg, field, value)
    if getattr(args, "user_sim", False):
        cfg.user_sim = True
    if getattr(args, "quiet", False):
        cfg.verbose = False
    return cfg


def _parse_seeds(raw: str) -> list[int]:
    seeds: list[int] = []
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        if "-" in chunk and not chunk.startswith("-"):
            start, _, end = chunk.partition("-")
            seeds.extend(range(int(start), int(end) + 1))
        else:
            seeds.append(int(chunk))
    return seeds


def _families(raw: str | None) -> list[str]:
    if not raw or raw == "all":
        return list(FAMILIES)
    chosen = [f.strip() for f in raw.split(",") if f.strip()]
    unknown = [f for f in chosen if f not in FAMILIES]
    if unknown:
        raise SystemExit(f"unknown families: {', '.join(unknown)}\nknown: {', '.join(FAMILIES)}")
    return chosen


# --------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------


def cmd_list(args: argparse.Namespace) -> int:
    width = max(len(f) for f in FAMILIES)
    print("Scenario families:\n")
    for family in FAMILIES:
        print(f"  {family:<{width}}  {scenarios.get(family).summary}")
    print(f"\nHint levels: {scenarios.HINT_LEVELS} (0 behavioural, 1 localising, 2 procedural)")
    print(f"Backends:    {', '.join(BACKEND_NAMES)}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    task = scenarios.build(args.family, args.seed, args.hint)
    if args.json:
        print(json.dumps(task.to_json(), indent=2))
        return 0
    print(f"# {task.task_id}\n")
    print(task.brief)
    print("## Parameters\n")
    print(json.dumps(task.params, indent=2))
    return 0


def cmd_materialize(args: argparse.Namespace) -> int:
    task = scenarios.build(args.family, args.seed, args.hint)
    workspace = grader.materialize(task)
    print(f"workspace:    {workspace}")
    print(f"hidden tests: {grader.hidden_test_path(task)}")
    if args.gold:
        grader.apply_gold(task)
        print("gold solution applied")
    print(grader.grade(task).summary())
    return 0


def cmd_run(args: argparse.Namespace) -> int:
    cfg = _agent_config(args)
    task = scenarios.build(args.family, args.seed, args.hint)
    print(f"task:    {task.task_id}")
    print(f"backend: {cfg.backend} model={cfg.model} max_steps={cfg.max_steps}\n")
    try:
        result = run_task(task, cfg)
    except BackendError as exc:
        print(f"backend unreachable: {exc}", file=sys.stderr)
        return 2
    print()
    print(result.grade.summary())
    print(json.dumps(result.episode.metrics.to_json(), indent=2))
    if result.episode.transcript_path:
        print(f"transcript: {result.episode.transcript_path}")
    return 0 if result.reward else 1


def cmd_eval(args: argparse.Namespace) -> int:
    cfg = _agent_config(args)
    cfg.verbose = args.verbose
    families = _families(args.families)
    seeds = _parse_seeds(args.seeds)
    rows = []
    for family in families:
        for seed in seeds:
            task = scenarios.build(family, seed, args.hint)
            try:
                result = run_task(task, cfg, save_transcript=not args.no_transcript)
            except BackendError as exc:
                print(f"backend unreachable: {exc}", file=sys.stderr)
                return 2
            metrics = result.episode.metrics
            rows.append(
                {
                    "task": task.task_id,
                    "reward": result.reward,
                    "steps": metrics.steps,
                    "verified": int(metrics.verified_before_stop),
                    "single_tool": metrics.single_tool_turn_rate,
                    "errors": metrics.tool_errors + metrics.unknown_tools,
                    "seconds": metrics.wall_seconds,
                }
            )
            print(
                f"{task.task_id:<34} reward={result.reward} steps={metrics.steps:>3} "
                f"verified={int(metrics.verified_before_stop)} "
                f"errors={metrics.tool_errors + metrics.unknown_tools} "
                f"{metrics.wall_seconds:>7.1f}s"
            )

    if not rows:
        print("nothing ran")
        return 1
    solved = sum(r["reward"] for r in rows)
    print("\n" + "=" * 68)
    print(f"solved {solved}/{len(rows)} = {solved / len(rows):.1%}")
    print(f"verified before stopping: {statistics.fmean(r['verified'] for r in rows):.1%}")
    print(f"single-tool turns:        {statistics.fmean(r['single_tool'] for r in rows):.1%}")
    print(f"mean wall time:           {statistics.fmean(r['seconds'] for r in rows):.1f}s")
    by_family: dict[str, list[int]] = {}
    for row in rows:
        by_family.setdefault(row["task"].rsplit("-", 2)[0], []).append(row["reward"])
    print("\nby family:")
    for family, rewards in by_family.items():
        print(f"  {family:<20} {sum(rewards)}/{len(rewards)}")
    if args.out:
        Path(args.out).write_text(json.dumps(rows, indent=2) + "\n")
        print(f"\nwrote {args.out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Check that generated tasks behave like tasks: F2P fails, P2P passes, gold wins."""
    families = _families(args.families)
    seeds = _parse_seeds(args.seeds)
    bad = 0
    for family in families:
        for seed in seeds:
            task = scenarios.build(family, seed, args.hint)
            validity = grader.validate_task(task)
            flag = "ok " if validity.ok else "BAD"
            if not validity.ok:
                bad += 1
            print(f"{flag} {validity.task_id:<34} {validity.detail[:120]}")
    total = len(families) * len(seeds)
    print(f"\n{total - bad}/{total} tasks well-posed")
    return 1 if bad else 0


def cmd_taskpilot(args: argparse.Namespace) -> int:
    cfg = _agent_config(args)
    cfg.verbose = args.verbose
    tp = TaskPilotConfig()
    for field in ("rollouts", "iterations", "candidates_per_iteration"):
        value = getattr(args, field, None)
        if value is not None:
            setattr(tp, field, value)
    tp.max_steps = args.max_steps or tp.max_steps
    cfg.max_steps = tp.max_steps
    reports = taskpilot.run_curriculum(cfg, tp, families=_families(args.families))
    print("\n" + "=" * 68)
    for report in reports:
        print(f"iteration {report.index}: {report.summary()}")
    print(f"\nadmitted task set: {config_mod.TASKS_DIR / 'admitted.json'}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """Check that this machine can actually run an episode."""
    import shutil
    import subprocess

    print(f"python:       {sys.version.split()[0]} ({sys.executable})")
    try:
        import pytest  # noqa: F401

        print(f"pytest:       {pytest.__version__}")
    except ImportError:
        print("pytest:       MISSING — `pip install pytest`, grading cannot run without it")

    print(f"workspace:    {config_mod.WORKSPACE}")
    print(f"hidden tests: {config_mod.HIDDEN_TESTS}")
    print(f"runs:         {config_mod.RUNS_DIR}")
    print(f"sh:           {shutil.which('sh') or 'MISSING'}")

    cfg = _agent_config(args)
    print(f"\nbackend:      {cfg.backend} model={cfg.model}")
    if cfg.backend in {"gold", "noop"}:
        print("              offline backend, nothing to reach")
        return 0
    backend = make_backend(cfg, task=None, workspace=None) if cfg.backend != "gold" else None
    base = getattr(backend, "base_url", "?")
    print(f"endpoint:     {base}")
    try:
        reply = backend.chat([{"role": "user", "content": "Reply with the word ok."}], [])
        print(f"reachable:    yes — {reply.content.strip()[:80]!r}")
    except BackendError as exc:
        print(f"reachable:    NO — {exc}")
        if cfg.backend == "ollama":
            print("              start it with `ollama serve`, then `ollama pull qwen3.5:4b`")
        else:
            print("              start llama-server with --jinja, or set LEAFCX_BASE_URL")
        return 2
    try:
        subprocess.run(["uname", "-a"], capture_output=True, check=False)
    except FileNotFoundError:
        pass
    return 0


# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python3 -m leafcx",
        description="Leaf + TaskPilot (arXiv:2609.07925) for self-serve account management.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    def add_model_flags(p: argparse.ArgumentParser) -> None:
        p.add_argument("--backend", choices=list(BACKEND_NAMES), help="default: ollama")
        p.add_argument("--model", help="default: qwen3.5:4b")
        p.add_argument("--base-url", dest="base_url", help="model server URL")
        p.add_argument("--max-steps", type=int, help="tool-call budget per episode")
        p.add_argument("--temperature", type=float)
        p.add_argument("--user-sim", action="store_true", help="enable the simulated customer")

    p_list = sub.add_parser("list", help="list scenario families")
    p_list.set_defaults(func=cmd_list)

    p_show = sub.add_parser("show", help="print a task's brief and parameters")
    p_show.add_argument("family", choices=list(FAMILIES))
    p_show.add_argument("--seed", type=int, default=1)
    p_show.add_argument("--hint", type=int, default=0, choices=list(scenarios.HINT_LEVELS))
    p_show.add_argument("--json", action="store_true")
    p_show.set_defaults(func=cmd_show)

    p_mat = sub.add_parser("materialize", help="write a task's workspace without running an agent")
    p_mat.add_argument("family", choices=list(FAMILIES))
    p_mat.add_argument("--seed", type=int, default=1)
    p_mat.add_argument("--hint", type=int, default=0, choices=list(scenarios.HINT_LEVELS))
    p_mat.add_argument("--gold", action="store_true", help="also apply the reference solution")
    p_mat.set_defaults(func=cmd_materialize)

    p_run = sub.add_parser("run", help="run one episode and grade it")
    p_run.add_argument("family", choices=list(FAMILIES))
    p_run.add_argument("--seed", type=int, default=1)
    p_run.add_argument("--hint", type=int, default=0, choices=list(scenarios.HINT_LEVELS))
    p_run.add_argument("--quiet", action="store_true")
    add_model_flags(p_run)
    p_run.set_defaults(func=cmd_run)

    p_eval = sub.add_parser("eval", help="run a batch of tasks and report solve rate")
    p_eval.add_argument("--families", default="all")
    p_eval.add_argument("--seeds", default="1-5")
    p_eval.add_argument("--hint", type=int, default=0, choices=list(scenarios.HINT_LEVELS))
    p_eval.add_argument("--verbose", action="store_true", help="stream every tool call")
    p_eval.add_argument("--no-transcript", action="store_true")
    p_eval.add_argument("--out", help="write per-task results as JSON")
    add_model_flags(p_eval)
    p_eval.set_defaults(func=cmd_eval)

    p_val = sub.add_parser("validate", help="check generated tasks are well-posed")
    p_val.add_argument("--families", default="all")
    p_val.add_argument("--seeds", default="1-5")
    p_val.add_argument("--hint", type=int, default=0, choices=list(scenarios.HINT_LEVELS))
    p_val.set_defaults(func=cmd_validate)

    p_tp = sub.add_parser("taskpilot", help="run the learnability-frontier curriculum")
    p_tp.add_argument("--families", default="all")
    p_tp.add_argument("--rollouts", type=int)
    p_tp.add_argument("--iterations", type=int)
    p_tp.add_argument("--candidates-per-iteration", dest="candidates_per_iteration", type=int)
    p_tp.add_argument("--verbose", action="store_true")
    add_model_flags(p_tp)
    p_tp.set_defaults(func=cmd_taskpilot)

    p_doc = sub.add_parser("doctor", help="check this machine can run an episode")
    add_model_flags(p_doc)
    p_doc.set_defaults(func=cmd_doctor)

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
