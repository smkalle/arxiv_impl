"""L2 Ingestor AutoResearch Loop."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from dev_set import DevSetConfig, DevSetEvaluator
from ingestor import IngestorConfig, KBIngestor
from loops.action_space import RetrievalConfig
from loops.failure_logger import FailureLogger
from loops.l2_ingestor.diagnosis import run_l2_diagnosis
from loops.l2_ingestor.editor import L2Editor
from loops.llm import LLMProvider, extract_json
from loops.loop_runner import BaseLoop


class L2Loop(BaseLoop):
    loop_id = "L2"
    loop_name = "Memory Quality"
    edit_target = "IngestorConfig"
    fitness_metric = "synthesis_ratio × F1 ceiling"

    def __init__(
        self,
        router: Any,
        llm: LLMProvider,
        failure_logger: FailureLogger,
        state_path: Path,
        kb_path: Path,
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
        self._kb_path = kb_path
        self._dev_set_path = dev_set_path
        self._evolved_dir = evolved_dir
        self._dev_config = dev_config or DevSetConfig()
        self._settings = settings
        self._editor = L2Editor()

        state = self._load_state()
        self._ingestor_config = IngestorConfig.from_dict(
            state.get("current_config", {})
        )
        self._prev_config = self._ingestor_config
        self._last_synthesis_ratio = 0.0
        self._last_f1_ceiling = 0.0

    def measure_fitness(self) -> float:
        # Re-ingest with current config
        self._router.create("text")
        ingestor = KBIngestor(self._router, self._ingestor_config)
        stats = ingestor.ingest_csv(self._kb_path)
        ingestor.finalize()
        self._last_synthesis_ratio = stats["synthesis_ratio"]

        # Quick L3 sub-run to measure F1 ceiling
        from loops.l3_retrieval.loop import L3Loop
        l3 = L3Loop(
            router=self._router,
            llm=self._llm,
            failure_logger=self._failure_logger,
            state_path=self._evolved_dir / "_l3_quick_state.json",
            dev_set_path=self._dev_set_path,
            evolved_dir=self._evolved_dir,
            dev_config=self._dev_config,
            quick_mode=True,
        )
        result = l3.run()
        self._last_f1_ceiling = result.best_fitness

        return self._last_synthesis_ratio * self._last_f1_ceiling

    def generate_diagnosis(
        self,
        fitness: float,
        history: list[float],
        stagnating: bool,
    ) -> str:
        return run_l2_diagnosis(
            self._llm,
            self._ingestor_config,
            self._last_synthesis_ratio,
            self._last_f1_ceiling,
            fitness,
            history,
            stagnating,
        )

    def parse_action(self, diagnosis: str) -> dict[str, Any]:
        return extract_json(diagnosis)

    def apply_action(self, action: dict[str, Any]) -> None:
        self._prev_config = self._ingestor_config
        self._ingestor_config = self._editor.apply(self._ingestor_config, action)

    def revert_action(self, action: dict[str, Any]) -> None:
        self._ingestor_config = self._prev_config

    def _get_final_config(self) -> dict[str, Any]:
        return self._ingestor_config.to_dict()

    def run(self):  # type: ignore[override]
        result = super().run()
        self._evolved_dir.mkdir(parents=True, exist_ok=True)
        out = self._evolved_dir / "ingestor_config.json"
        out.write_text(json.dumps(result.final_config, indent=2))
        return result
