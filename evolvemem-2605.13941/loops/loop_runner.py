"""
BaseLoop — abstract template shared by all four AutoResearch loops.
run_all_loops() — sequences L1 → L2 → L3 → L4.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loops.failure_logger import FailureLogger
from loops.llm import LLMProvider
from loops.meta_analyzer import MetaAnalyzer


# ── Loop result ──────────────────────────────────────────────────────────────

class LoopResult:
    def __init__(
        self,
        loop_id: str,
        rounds_run: int,
        fitness_history: list[float],
        best_fitness: float,
        baseline_fitness: float,
        final_config: dict[str, Any],
        accepted_patches: list[dict],
        discovered_dimensions: list[str],
    ) -> None:
        self.loop_id = loop_id
        self.rounds_run = rounds_run
        self.fitness_history = fitness_history
        self.best_fitness = best_fitness
        self.baseline_fitness = baseline_fitness
        self.final_config = final_config
        self.accepted_patches = accepted_patches
        self.discovered_dimensions = discovered_dimensions

    def to_dict(self) -> dict[str, Any]:
        return {
            "loop_id": self.loop_id,
            "rounds_run": self.rounds_run,
            "fitness_history": self.fitness_history,
            "best_fitness": self.best_fitness,
            "baseline_fitness": self.baseline_fitness,
            "final_config": self.final_config,
            "accepted_patches": self.accepted_patches,
            "discovered_dimensions": self.discovered_dimensions,
        }


# ── Base loop ────────────────────────────────────────────────────────────────

class BaseLoop(ABC):
    loop_id: str
    loop_name: str
    edit_target: str
    fitness_metric: str

    def __init__(
        self,
        llm: LLMProvider,
        failure_logger: FailureLogger,
        state_path: Path,
        max_rounds: int,
        quick_mode: bool = False,
    ) -> None:
        self._llm = llm
        self._failure_logger = failure_logger
        self._state_path = state_path
        self.max_rounds = max_rounds
        self._quick_mode = quick_mode
        self._meta = MetaAnalyzer()

    # ── Abstract interface ───────────────────────────────────────────────────

    @abstractmethod
    def measure_fitness(self) -> float:
        """Compute the fitness metric for the current edit target state."""

    @abstractmethod
    def generate_diagnosis(
        self,
        fitness: float,
        history: list[float],
        stagnating: bool,
    ) -> str:
        """Call the LLM to propose a patch given current fitness and history."""

    @abstractmethod
    def parse_action(self, diagnosis: str) -> dict[str, Any]:
        """Parse the LLM output into a patch dict."""

    @abstractmethod
    def apply_action(self, action: dict[str, Any]) -> None:
        """Apply the patch to the edit target."""

    @abstractmethod
    def revert_action(self, action: dict[str, Any]) -> None:
        """Undo the last applied patch."""

    @abstractmethod
    def _get_final_config(self) -> dict[str, Any]:
        """Return serializable dict of current edit target state."""

    def _get_discovered_dimensions(self) -> list[str]:
        return []

    # ── Template method ──────────────────────────────────────────────────────

    def run(self) -> LoopResult:
        state = self._load_state()
        history: list[float] = state.get("fitness_history", [])
        accepted: list[dict] = state.get("accepted_patches", [])
        start_round: int = state.get("rounds_done", 0)

        # Baseline on first run
        if start_round == 0:
            baseline = self.measure_fitness()
            history.append(baseline)
            if not self._quick_mode:
                self._save_state(0, history, accepted)
        else:
            baseline = state.get("baseline_fitness", history[0] if history else 0.0)

        for round_no in range(start_round, self.max_rounds):
            current_fitness = history[-1] if history else 0.0

            diagnosis = self.generate_diagnosis(
                current_fitness,
                history,
                self._meta.stagnating,
            )
            action = self.parse_action(diagnosis)

            if not action:
                # LLM returned empty patch — skip round
                history.append(current_fitness)
                self._save_state(round_no + 1, history, accepted)
                continue

            self.apply_action(action)
            fitness_after = self.measure_fitness()
            decision, reason = self._meta.evaluate(current_fitness, fitness_after)

            if decision in ("revert", "reject"):
                self.revert_action(action)
                self._failure_logger.log(
                    self.loop_id, round_no,
                    current_fitness, fitness_after,
                    action, diagnosis, False, reason,
                )
                history.append(current_fitness)
            else:
                accepted.append({**action, "__round": round_no, "__decision": decision})
                self._failure_logger.log(
                    self.loop_id, round_no,
                    current_fitness, fitness_after,
                    action, diagnosis, True, None,
                )
                history.append(fitness_after)

            if not self._quick_mode:
                self._save_state(round_no + 1, history, accepted)

        result = LoopResult(
            loop_id=self.loop_id,
            rounds_run=self.max_rounds,
            fitness_history=history,
            best_fitness=max(history) if history else 0.0,
            baseline_fitness=baseline,
            final_config=self._get_final_config(),
            accepted_patches=accepted,
            discovered_dimensions=self._get_discovered_dimensions(),
        )

        if not self._quick_mode:
            self._write_complete_state(result)

        return result

    def is_complete(self) -> bool:
        state = self._load_state()
        return state.get("status") == "complete"

    # ── State persistence ────────────────────────────────────────────────────

    def _load_state(self) -> dict[str, Any]:
        if self._state_path.exists():
            try:
                return json.loads(self._state_path.read_text())
            except (json.JSONDecodeError, OSError):
                pass
        return {}

    def _save_state(
        self,
        rounds_done: int,
        history: list[float],
        accepted: list[dict],
    ) -> None:
        state = {
            "loop_id": self.loop_id,
            "loop_name": getattr(self, "loop_name", self.loop_id),
            "edit_target": getattr(self, "edit_target", ""),
            "fitness_metric": getattr(self, "fitness_metric", ""),
            "status": "running",
            "rounds_done": rounds_done,
            "max_rounds": self.max_rounds,
            "baseline_fitness": history[0] if history else 0.0,
            "best_fitness": max(history) if history else 0.0,
            "fitness_history": history,
            "accepted_patches": accepted,
            "current_config": self._get_final_config(),
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2))

    def _write_complete_state(self, result: LoopResult) -> None:
        state = {
            **result.to_dict(),
            "status": "complete",
            "max_rounds": self.max_rounds,
            "last_updated": datetime.now(timezone.utc).isoformat(),
        }
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state, indent=2))


# ── Full four-loop orchestrator ───────────────────────────────────────────────

def run_all_loops(
    settings: Any,
    start_from: str = "L1",
    only: str | None = None,
) -> dict[str, LoopResult]:
    """
    Sequence L1 → L2 → L3 → L4.
    Each loop's output feeds the next.
    set start_from="L3" to skip L1/L2, only="L3" to run just L3.
    """
    from loops.l1_dev_set.loop import L1Loop
    from loops.l2_ingestor.loop import L2Loop
    from loops.l3_retrieval.loop import L3Loop
    from loops.l4_prompt.loop import L4Loop
    from loops.llm import get_provider
    from simplemem_router import SimplememRouter
    from ingestor import KBIngestor, IngestorConfig
    from dev_set import DevSetEvaluator, DevSetConfig

    data_dir = Path(settings.data_dir) if isinstance(settings.data_dir, str) else settings.data_dir
    failure_logger = FailureLogger(data_dir / "failure_log.jsonl")
    llm = get_provider(
        provider=settings.diagnosis_llm_provider,
        model=settings.diagnosis_llm_model,
        api_key=getattr(settings, "anthropic_api_key", ""),
        host=getattr(settings, "ollama_host", "http://localhost:11434"),
    )

    router = SimplememRouter(settings)
    router.create("text")
    ingestor = KBIngestor(router, IngestorConfig())
    ingestor.ingest_csv(data_dir / "raw" / "kb_articles.csv")
    ingestor.finalize()

    sequence = (
        [only] if only
        else ["L1", "L2", "L3", "L4"][["L1", "L2", "L3", "L4"].index(start_from):]
    )

    results: dict[str, LoopResult] = {}
    evolved_dev_config = DevSetConfig()

    for loop_id in sequence:
        if loop_id == "L1":
            loop = L1Loop(
                router=router,
                llm=llm,
                failure_logger=failure_logger,
                state_path=data_dir / "loop_states" / "l1_state.json",
                dev_set_path=data_dir / "dev_set.json",
                evolved_dir=data_dir / "evolved",
            )
            if not loop.is_complete():
                results["L1"] = loop.run()
            evolved_dev_config = DevSetConfig.from_dict(
                json.loads((data_dir / "evolved" / "dev_set_config.json").read_text())
                if (data_dir / "evolved" / "dev_set_config.json").exists()
                else {}
            )

        elif loop_id == "L2":
            loop = L2Loop(
                router=router,
                llm=llm,
                failure_logger=failure_logger,
                state_path=data_dir / "loop_states" / "l2_state.json",
                kb_path=data_dir / "raw" / "kb_articles.csv",
                dev_set_path=data_dir / "dev_set.json",
                evolved_dir=data_dir / "evolved",
                dev_config=evolved_dev_config,
                settings=settings,
            )
            if not loop.is_complete():
                results["L2"] = loop.run()

        elif loop_id == "L3":
            loop = L3Loop(
                router=router,
                llm=llm,
                failure_logger=failure_logger,
                state_path=data_dir / "loop_states" / "l3_state.json",
                dev_set_path=data_dir / "dev_set.json",
                evolved_dir=data_dir / "evolved",
                dev_config=evolved_dev_config,
            )
            if not loop.is_complete():
                results["L3"] = loop.run()

        elif loop_id == "L4":
            loop = L4Loop(
                router=router,
                llm=llm,
                failure_logger=failure_logger,
                state_path=data_dir / "loop_states" / "l4_state.json",
                dev_set_path=data_dir / "dev_set.json",
                evolved_dir=data_dir / "evolved",
                dev_config=evolved_dev_config,
                settings=settings,
            )
            if not loop.is_complete():
                results["L4"] = loop.run()

    return results
