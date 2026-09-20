"""Runtime configuration.

Everything here is overridable by environment variable so the same code runs on
a phone (Termux + llama.cpp), on a laptop (Ollama), or in CI (no model at all).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

#: Root of this subproject on disk.
PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: Where an episode's mutable account workspace is materialised.  The agent's
#: file tools are confined to this directory.
WORKSPACE = Path(os.environ.get("LEAFCX_WORKSPACE", PROJECT_ROOT / "workspace")).resolve()

#: Where generated hidden tests live.  Deliberately a *sibling* of WORKSPACE so
#: no relative path inside the workspace can reach it.
HIDDEN_TESTS = Path(os.environ.get("LEAFCX_HIDDEN_TESTS", PROJECT_ROOT / "hidden_tests")).resolve()

#: TaskPilot output (admitted task sets, per-iteration statistics).
TASKS_DIR = Path(os.environ.get("LEAFCX_TASKS", PROJECT_ROOT / "tasks")).resolve()

#: Episode transcripts (JSONL, one file per run).
RUNS_DIR = Path(os.environ.get("LEAFCX_RUNS", PROJECT_ROOT / "runs")).resolve()


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class AgentConfig:
    """Sampling and budget settings for one episode.

    Defaults follow the paper's *evaluation* settings, not its training
    settings.  Training used ``temperature=1.0, top_p=1.0`` for exploration;
    shipping an agent at those values produces noise.
    """

    backend: str = field(default_factory=lambda: os.environ.get("LEAFCX_BACKEND", "ollama"))
    model: str = field(default_factory=lambda: os.environ.get("LEAFCX_MODEL", "qwen3.5:4b"))
    base_url: str = field(default_factory=lambda: os.environ.get("LEAFCX_BASE_URL", ""))
    api_key: str = field(default_factory=lambda: os.environ.get("LEAFCX_API_KEY", "not-needed"))

    temperature: float = field(default_factory=lambda: _env_float("LEAFCX_TEMPERATURE", 0.6))
    top_p: float = field(default_factory=lambda: _env_float("LEAFCX_TOP_P", 0.95))
    num_ctx: int = field(default_factory=lambda: _env_int("LEAFCX_NUM_CTX", 32768))
    num_predict: int = field(default_factory=lambda: _env_int("LEAFCX_NUM_PREDICT", 4096))

    #: Paper eval used ~53 steps/task at 131k context.  40 is a sane phone budget.
    max_steps: int = field(default_factory=lambda: _env_int("LEAFCX_MAX_STEPS", 40))
    #: Hard cap on a single tool result fed back into the transcript.
    max_tool_chars: int = field(default_factory=lambda: _env_int("LEAFCX_MAX_TOOL_CHARS", 12000))
    #: Wall-clock seconds for one `bash` invocation.
    bash_timeout: int = field(default_factory=lambda: _env_int("LEAFCX_BASH_TIMEOUT", 30))
    #: HTTP timeout when talking to the model server.  A 4B Q4 model on a phone
    #: is slow; do not set this low.
    request_timeout: int = field(default_factory=lambda: _env_int("LEAFCX_REQUEST_TIMEOUT", 600))

    #: Enable the simulated customer (`ask_customer` tool).  Off by default:
    #: v1 tasks hand the agent a written brief and it works single-shot.
    user_sim: bool = field(
        default_factory=lambda: os.environ.get("LEAFCX_USER_SIM", "").lower() in {"1", "true", "yes"}
    )
    #: Budget on `ask_customer` calls, so a confused policy cannot loop forever.
    user_sim_max_turns: int = field(default_factory=lambda: _env_int("LEAFCX_USER_SIM_MAX_TURNS", 6))

    verbose: bool = field(
        default_factory=lambda: os.environ.get("LEAFCX_VERBOSE", "1").lower() not in {"0", "false", "no"}
    )


@dataclass
class TaskPilotConfig:
    """Curriculum settings.

    The paper ran ~300 candidate tasks per iteration with 5 iterations; iters 1-4
    targeted a solve rate near 0.5 and iter 5 widened the band to ``0 < p <= 0.5``.
    """

    rollouts: int = field(default_factory=lambda: _env_int("LEAFCX_TP_ROLLOUTS", 4))
    iterations: int = field(default_factory=lambda: _env_int("LEAFCX_TP_ITERATIONS", 3))
    candidates_per_iteration: int = field(default_factory=lambda: _env_int("LEAFCX_TP_CANDIDATES", 12))
    #: Admission band for iterations 1..N-1 (centred on the learnability frontier).
    band_lo: float = field(default_factory=lambda: _env_float("LEAFCX_TP_BAND_LO", 0.15))
    band_hi: float = field(default_factory=lambda: _env_float("LEAFCX_TP_BAND_HI", 0.65))
    #: Final iteration keeps everything the policy has not mastered.
    final_band_lo: float = field(default_factory=lambda: _env_float("LEAFCX_TP_FINAL_LO", 0.0))
    final_band_hi: float = field(default_factory=lambda: _env_float("LEAFCX_TP_FINAL_HI", 0.5))
    #: Steps allowed per curriculum rollout (cheaper than a real eval episode).
    max_steps: int = field(default_factory=lambda: _env_int("LEAFCX_TP_MAX_STEPS", 25))
    seed: int = field(default_factory=lambda: _env_int("LEAFCX_TP_SEED", 20260920))
