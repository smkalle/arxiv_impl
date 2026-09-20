"""One task, end to end: materialise, run the episode, grade it."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from . import config as config_mod
from . import grader
from .agent import EpisodeResult, run_episode, write_transcript
from .backends import make_backend
from .config import AgentConfig
from .scenarios import TaskInstance


@dataclass
class RunResult:
    task: TaskInstance
    episode: EpisodeResult
    grade: grader.GradeResult

    @property
    def reward(self) -> int:
        return self.grade.reward

    def to_json(self) -> dict[str, Any]:
        return {
            "task": self.task.to_json(),
            "reward": self.reward,
            "metrics": self.episode.metrics.to_json(),
            "grade": self.grade.to_json(),
            "final_message": self.episode.final_message,
            "transcript": str(self.episode.transcript_path) if self.episode.transcript_path else None,
        }


def run_task(
    task: TaskInstance,
    cfg: AgentConfig | None = None,
    workspace: Path | None = None,
    hidden_dir: Path | None = None,
    save_transcript: bool = True,
    on_event: Callable[[str], None] | None = None,
) -> RunResult:
    """Reset the workspace, run one episode, grade the final state."""
    cfg = cfg or AgentConfig()
    workspace = Path(workspace or config_mod.WORKSPACE)
    hidden_dir = Path(hidden_dir or config_mod.HIDDEN_TESTS)

    grader.materialize(task, workspace, hidden_dir)
    backend = make_backend(cfg, task=task, workspace=workspace)
    episode = run_episode(task, cfg, backend=backend, workspace=workspace, on_event=on_event)
    result = grader.grade(task, workspace, hidden_dir)
    if save_transcript:
        write_transcript(episode)
    return RunResult(task=task, episode=episode, grade=result)
