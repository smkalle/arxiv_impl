"""TaskPilot: keep the tasks the policy can *almost* do.

The paper's curriculum does not dump candidate tasks into the buffer. For each
candidate it rolls the current policy out N times, estimates the solve rate p̂,
and admits the task only if p̂ sits on the learnability frontier. Iterations 1-4
targeted p̂ ≈ 0.5; iteration 5 widened to 0 < p̂ ≤ 0.5. Too easy or too hard gets
refined or dropped, ~300 candidates per iteration.

This is that control loop at laptop and phone scale. One honest caveat: without
the RL half, the policy does not change between iterations, so p̂ drifts only
through refinement and sampling noise. The refinement ladder is the part that
still does real work locally — and the paper's own worked example is exactly a
ladder: an underspecified statement solved 0% of the time, a behavioural one
about 50%, a solution-localising one 100% and therefore too easy to keep.
"""

from __future__ import annotations

import json
import statistics
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

from . import config as config_mod
from .config import AgentConfig, TaskPilotConfig
from .runner import run_task
from .scenarios import FAMILIES, HINT_LEVELS, TaskInstance, build

#: What to do with a candidate after estimating its solve rate.
KEEP = "keep"
MAKE_EASIER = "make_easier"
MAKE_HARDER = "make_harder"
DROP = "drop"


@dataclass
class Candidate:
    """A task plus what the current policy did with it."""

    task_id: str
    family: str
    seed: int
    hint_level: int
    p_hat: float
    rewards: list[int]
    verdict: str
    wall_seconds: float = 0.0
    verified_before_stop: float = 0.0
    single_tool_turn_rate: float = 0.0

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class IterationReport:
    index: int
    band: tuple[float, float]
    candidates: list[Candidate] = field(default_factory=list)
    admitted: list[Candidate] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {
            "iteration": self.index,
            "band": list(self.band),
            "candidates": [c.to_json() for c in self.candidates],
            "admitted": [c.to_json() for c in self.admitted],
            "summary": self.summary(),
        }

    def summary(self) -> dict[str, Any]:
        rates = [c.p_hat for c in self.candidates]
        return {
            "candidates": len(self.candidates),
            "admitted": len(self.admitted),
            "mean_p_hat": round(statistics.fmean(rates), 4) if rates else 0.0,
            "solved_always": sum(1 for r in rates if r >= 1.0),
            "solved_never": sum(1 for r in rates if r <= 0.0),
        }


def estimate_solve_rate(
    task: TaskInstance,
    cfg: AgentConfig,
    rollouts: int,
    on_event: Callable[[str], None] | None = None,
) -> tuple[float, list[int], dict[str, float]]:
    """Roll the policy out `rollouts` times on a freshly reset workspace each time.

    A single rollout is not an estimate. The paper uses p̂ precisely because a
    4B policy solves a given task on some seeds and misses it on others.
    """
    rewards: list[int] = []
    verified: list[int] = []
    single_tool: list[float] = []
    elapsed = 0.0
    for index in range(rollouts):
        # Per-tool-call logging follows cfg.verbose; `on_event` here is the
        # curriculum's own progress channel and should stay one line per rollout.
        result = run_task(task, cfg, save_transcript=False)
        rewards.append(result.reward)
        verified.append(int(result.episode.metrics.verified_before_stop))
        single_tool.append(result.episode.metrics.single_tool_turn_rate)
        elapsed += result.episode.metrics.wall_seconds
        if on_event:
            on_event(f"    rollout {index + 1}/{rollouts} reward={result.reward}")
    p_hat = sum(rewards) / len(rewards) if rewards else 0.0
    stats = {
        "wall_seconds": round(elapsed, 2),
        "verified_before_stop": round(sum(verified) / len(verified), 4) if verified else 0.0,
        "single_tool_turn_rate": round(statistics.fmean(single_tool), 4) if single_tool else 0.0,
    }
    return p_hat, rewards, stats


def classify(p_hat: float, band: tuple[float, float], hint_level: int) -> str:
    """Admit, refine or drop, following the paper's frontier logic.

    A task the policy never solves is not thrown away first — it is made more
    localising, because "too hard" is usually "underspecified". A task solved
    every time is made behavioural again, and dropped if it is already as
    behavioural as the family gets.
    """
    lo, hi = band
    if lo < p_hat < hi:
        return KEEP
    if p_hat <= lo:
        return MAKE_EASIER if hint_level < max(HINT_LEVELS) else DROP
    return MAKE_HARDER if hint_level > min(HINT_LEVELS) else DROP


def refine(task: TaskInstance, verdict: str) -> TaskInstance | None:
    """Re-draw the same task instance at a different hint level."""
    if verdict == MAKE_EASIER and task.hint_level < max(HINT_LEVELS):
        return build(task.family, task.seed, task.hint_level + 1)
    if verdict == MAKE_HARDER and task.hint_level > min(HINT_LEVELS):
        return build(task.family, task.seed, task.hint_level - 1)
    return None


def candidate_tasks(
    families: Iterable[str],
    count: int,
    seed_base: int,
    hint_level: int = 0,
) -> list[TaskInstance]:
    """Draw `count` candidates, cycling through the families."""
    families = list(families) if families else list(FAMILIES)
    tasks: list[TaskInstance] = []
    for index in range(count):
        family = families[index % len(families)]
        tasks.append(build(family, seed_base + index, hint_level))
    return tasks


def run_iteration(
    index: int,
    tasks: list[TaskInstance],
    cfg: AgentConfig,
    tp: TaskPilotConfig,
    band: tuple[float, float],
    on_event: Callable[[str], None] | None = None,
) -> IterationReport:
    """Estimate p̂ for each candidate, then admit, refine or drop it."""
    log = on_event or (lambda line: None)
    report = IterationReport(index=index, band=band)
    queue = list(tasks)
    refined_once: set[str] = set()

    while queue:
        task = queue.pop(0)
        log(f"  [{task.task_id}] estimating p̂ over {tp.rollouts} rollouts")
        p_hat, rewards, stats = estimate_solve_rate(task, cfg, tp.rollouts, on_event=log)
        verdict = classify(p_hat, band, task.hint_level)
        candidate = Candidate(
            task_id=task.task_id,
            family=task.family,
            seed=task.seed,
            hint_level=task.hint_level,
            p_hat=p_hat,
            rewards=rewards,
            verdict=verdict,
            wall_seconds=stats["wall_seconds"],
            verified_before_stop=stats["verified_before_stop"],
            single_tool_turn_rate=stats["single_tool_turn_rate"],
        )
        report.candidates.append(candidate)
        log(f"  [{task.task_id}] p̂={p_hat:.2f} -> {verdict}")

        if verdict == KEEP:
            report.admitted.append(candidate)
            continue
        # Refine each seed at most once per iteration, or a task that is stuck
        # at 0 would walk the whole ladder inside one pass.
        key = f"{task.family}:{task.seed}"
        if key in refined_once:
            continue
        replacement = refine(task, verdict)
        if replacement is not None:
            refined_once.add(key)
            log(f"  [{task.task_id}] refined to hint_level={replacement.hint_level}")
            queue.append(replacement)

    return report


def run_curriculum(
    cfg: AgentConfig | None = None,
    tp: TaskPilotConfig | None = None,
    families: Iterable[str] | None = None,
    tasks_dir: Path | None = None,
    on_event: Callable[[str], None] | None = None,
) -> list[IterationReport]:
    """Run the full curriculum and write one JSON report per iteration."""
    cfg = cfg or AgentConfig()
    tp = tp or TaskPilotConfig()
    tasks_dir = Path(tasks_dir or config_mod.TASKS_DIR)
    tasks_dir.mkdir(parents=True, exist_ok=True)
    log = on_event or (lambda line: print(line))

    reports: list[IterationReport] = []
    for index in range(1, tp.iterations + 1):
        # Final iteration keeps everything the policy has not yet mastered,
        # matching the paper's widened band on its last pass.
        band = (
            (tp.final_band_lo, tp.final_band_hi)
            if index == tp.iterations
            else (tp.band_lo, tp.band_hi)
        )
        log(f"== TaskPilot iteration {index}/{tp.iterations}  band={band}")
        tasks = candidate_tasks(
            families or FAMILIES,
            tp.candidates_per_iteration,
            seed_base=tp.seed + index * 1000,
        )
        report = run_iteration(index, tasks, cfg, tp, band, on_event=log)
        reports.append(report)

        path = tasks_dir / f"iteration_{index}.json"
        path.write_text(json.dumps(report.to_json(), indent=2) + "\n")
        log(f"   -> {report.summary()}  written to {path}")

    admitted = [c.to_json() for report in reports for c in report.admitted]
    (tasks_dir / "admitted.json").write_text(
        json.dumps({"generated_at": int(time.time()), "tasks": admitted}, indent=2) + "\n"
    )
    return reports
