"""L1 Dev Set AutoResearch Loop."""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any

from dev_set import DevSetConfig, DevSetEvaluator
from loops.action_space import RetrievalConfig
from loops.failure_logger import FailureLogger
from loops.l1_dev_set.diagnosis import run_l1_diagnosis
from loops.l1_dev_set.editor import L1Editor
from loops.llm import LLMProvider, extract_json
from loops.loop_runner import BaseLoop


class L1Loop(BaseLoop):
    loop_id = "L1"
    loop_name = "Dev Set Quality"
    edit_target = "DevSetConfig"
    fitness_metric = "F1 gain signal"

    def __init__(
        self,
        router: Any,
        llm: LLMProvider,
        failure_logger: FailureLogger,
        state_path: Path,
        dev_set_path: Path,
        evolved_dir: Path,
    ) -> None:
        super().__init__(
            llm=llm,
            failure_logger=failure_logger,
            state_path=state_path,
            max_rounds=3,
        )
        self._router = router
        self._dev_set_path = dev_set_path
        self._evolved_dir = evolved_dir
        self._editor = L1Editor()

        # Load state if resuming
        state = self._load_state()
        self._dev_config = DevSetConfig.from_dict(
            state.get("current_config", {})
        )
        self._prev_config = self._dev_config
        self._baseline_f1: float | None = None
        self._retrieval_config = RetrievalConfig()

    def measure_fitness(self) -> float:
        evaluator = DevSetEvaluator(self._dev_set_path, self._dev_config)
        evaluator.sample()
        return evaluator.compute_f1(self._router, self._retrieval_config)

    def generate_diagnosis(
        self,
        fitness: float,
        history: list[float],
        stagnating: bool,
    ) -> str:
        if self._baseline_f1 is None:
            self._baseline_f1 = fitness
        f1_gain = fitness - self._baseline_f1
        return run_l1_diagnosis(
            self._llm,
            self._dev_config,
            f1_gain,
            history,
            stagnating,
        )

    def parse_action(self, diagnosis: str) -> dict[str, Any]:
        return extract_json(diagnosis)

    def apply_action(self, action: dict[str, Any]) -> None:
        self._prev_config = self._dev_config
        self._dev_config = self._editor.apply(self._dev_config, action)

    def revert_action(self, action: dict[str, Any]) -> None:
        self._dev_config = self._prev_config

    def _get_final_config(self) -> dict[str, Any]:
        return self._dev_config.to_dict()

    def run(self):  # type: ignore[override]
        result = super().run()
        # Persist evolved config
        self._evolved_dir.mkdir(parents=True, exist_ok=True)
        out = self._evolved_dir / "dev_set_config.json"
        out.write_text(json.dumps(result.final_config, indent=2))
        return result
