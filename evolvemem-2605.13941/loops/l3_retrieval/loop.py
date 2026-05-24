"""L3 Retrieval Config AutoResearch Loop — the core loop."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dev_set import DevSetConfig, DevSetEvaluator
from loops.action_space import RetrievalConfig
from loops.failure_logger import FailureLogger
from loops.l3_retrieval.diagnosis import run_l3_diagnosis
from loops.l3_retrieval.editor import L3Editor
from loops.llm import LLMProvider, extract_json
from loops.loop_runner import BaseLoop


class L3Loop(BaseLoop):
    loop_id = "L3"
    loop_name = "Retrieval Config"
    edit_target = "RetrievalConfig"
    fitness_metric = "F1@5"

    def __init__(
        self,
        router: Any,
        llm: LLMProvider,
        failure_logger: FailureLogger,
        state_path: Path,
        dev_set_path: Path,
        evolved_dir: Path,
        dev_config: DevSetConfig | None = None,
        quick_mode: bool = False,
    ) -> None:
        super().__init__(
            llm=llm,
            failure_logger=failure_logger,
            state_path=state_path,
            max_rounds=1 if quick_mode else 7,
            quick_mode=quick_mode,
        )
        self._router = router
        self._dev_set_path = dev_set_path
        self._evolved_dir = evolved_dir
        self._dev_config = dev_config or DevSetConfig()
        self._editor = L3Editor()

        # Load config from state (for resume) or start fresh
        if not quick_mode:
            state = self._load_state()
            saved_cfg = state.get("current_config", {})
        else:
            saved_cfg = {}

        self._retrieval_config = (
            RetrievalConfig.from_dict(saved_cfg) if saved_cfg
            else RetrievalConfig()
        )
        self._prev_config = self._retrieval_config
        self._discovered: list[str] = []

        # L4 can override the diagnosis prompt at runtime
        self._diagnosis_prompt_override: str | None = None

    def set_diagnosis_prompt(self, prompt: str) -> None:
        self._diagnosis_prompt_override = prompt

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
        return run_l3_diagnosis(
            self._llm,
            self._retrieval_config,
            fitness,
            history,
            stagnating,
            prompt_override=self._diagnosis_prompt_override,
        )

    def parse_action(self, diagnosis: str) -> dict[str, Any]:
        return extract_json(diagnosis)

    def apply_action(self, action: dict[str, Any]) -> None:
        self._prev_config = self._retrieval_config
        new_config, new_dims = self._editor.apply(self._retrieval_config, action)
        self._retrieval_config = new_config
        self._discovered.extend(new_dims)

    def revert_action(self, action: dict[str, Any]) -> None:
        self._retrieval_config = self._prev_config

    def _get_final_config(self) -> dict[str, Any]:
        return self._retrieval_config.to_dict()

    def _get_discovered_dimensions(self) -> list[str]:
        return list(set(self._discovered))

    def run(self):  # type: ignore[override]
        result = super().run()
        if not self._quick_mode:
            self._evolved_dir.mkdir(parents=True, exist_ok=True)
            out = self._evolved_dir / "retrieval_config.json"
            out.write_text(json.dumps(result.final_config, indent=2))
        return result

    @property
    def current_config(self) -> RetrievalConfig:
        return self._retrieval_config
