"""Process-local singletons: RunStore + the PipelineExecutor."""

from __future__ import annotations

from threading import Lock

from metaorch.executor import PipelineExecutor
from metaorch.models import PipelineRun


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, PipelineRun] = {}
        self._lock = Lock()

    def put(self, run: PipelineRun) -> None:
        with self._lock:
            self._runs[run.run_id] = run

    def get(self, run_id: str) -> PipelineRun | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_ids(self) -> list[str]:
        with self._lock:
            return list(self._runs.keys())


_run_store: RunStore | None = None
_executor: PipelineExecutor | None = None


def get_run_store() -> RunStore:
    global _run_store
    if _run_store is None:
        _run_store = RunStore()
    return _run_store


def get_executor() -> PipelineExecutor:
    global _executor
    if _executor is None:
        _executor = PipelineExecutor()
    return _executor