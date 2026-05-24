"""L4 Prompt AutoResearch Loop — evolves the L3 DIAGNOSIS_SYSTEM_PROMPT."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Callable

from dev_set import DevSetConfig
from loops.failure_logger import FailureLogger
from loops.l3_retrieval import diagnosis as l3_diag_module
from loops.l4_prompt.diagnosis import run_l4_diagnosis
from loops.l4_prompt.editor import L4Editor
from loops.llm import LLMProvider
from loops.loop_runner import BaseLoop


class L4Loop(BaseLoop):
    loop_id = "L4"
    loop_name = "Diagnosis Prompt"
    edit_target = "DIAGNOSIS_SYSTEM_PROMPT"
    fitness_metric = "mean F1 delta / L3 round"

    def __init__(
        self,
        router: Any,
        llm: LLMProvider,
        failure_logger: FailureLogger,
        state_path: Path,
        dev_set_path: Path,
        evolved_dir: Path,
        dev_config: DevSetConfig | None = None,
        settings: Any = None,
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
        self._dev_config = dev_config or DevSetConfig()
        self._settings = settings
        self._editor = L4Editor()

        # Current prompt — start from L3's module-level constant
        state = self._load_state()
        self._current_prompt: str = state.get(
            "current_config", {}).get("prompt", l3_diag_module.DIAGNOSIS_SYSTEM_PROMPT
        )
        self._prev_prompt = self._current_prompt

    def _make_l3_loop(self):
        from loops.l3_retrieval.loop import L3Loop
        return L3Loop(
            router=self._router,
            llm=self._llm,
            failure_logger=self._failure_logger,
            state_path=self._evolved_dir / "_l4_l3_quick_state.json",
            dev_set_path=self._dev_set_path,
            evolved_dir=self._evolved_dir,
            dev_config=self._dev_config,
            quick_mode=True,
        )

    def measure_fitness(self) -> float:
        """Run 3 quick L3 rounds with current prompt; return mean F1 delta."""
        l3 = self._make_l3_loop()
        l3.set_diagnosis_prompt(self._current_prompt)
        # Run 3 rounds of quick L3
        l3.max_rounds = 3
        result = l3.run()
        history = result.fitness_history
        if len(history) < 2:
            return 0.0
        deltas = [history[i + 1] - history[i] for i in range(len(history) - 1)]
        return sum(deltas) / len(deltas)

    def generate_diagnosis(
        self,
        fitness: float,
        history: list[float],
        stagnating: bool,
    ) -> str:
        return run_l4_diagnosis(
            self._llm,
            self._current_prompt,
            fitness,
            history,
            stagnating,
        )

    def parse_action(self, diagnosis: str) -> dict[str, Any]:
        # L4 diagnosis output is the new prompt text directly (not JSON)
        return {"prompt": diagnosis}

    def apply_action(self, action: dict[str, Any]) -> None:
        self._prev_prompt = self._current_prompt
        new_prompt = self._editor.apply(self._current_prompt, action.get("prompt", ""))
        self._current_prompt = new_prompt

    def revert_action(self, action: dict[str, Any]) -> None:
        self._current_prompt = self._prev_prompt

    def _get_final_config(self) -> dict[str, Any]:
        return {"prompt": self._current_prompt}

    def run(self):  # type: ignore[override]
        result = super().run()
        self._evolved_dir.mkdir(parents=True, exist_ok=True)
        # Persist evolved prompt
        prompt_path = self._evolved_dir / "diagnosis_prompt.txt"
        self._editor.persist(self._current_prompt, prompt_path)
        # Also write state with the prompt
        out = self._evolved_dir / "l4_result.json"
        out.write_text(json.dumps(result.to_dict(), indent=2))
        return result
