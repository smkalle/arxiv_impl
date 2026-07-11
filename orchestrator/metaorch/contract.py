"""Configuration + the Adapter Protocol + the canonical DAG."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from metaorch.models import StageKind


# ---------------------------------------------------------------------------
# Canonical DAG: stage -> set of hard dependencies.
# CATALOG is a parallel root; it is NOT a hard dep of EVOLVE (spec §3, §O-1).
# ---------------------------------------------------------------------------

PIPELINE_DAG: dict[StageKind, frozenset[StageKind]] = {
    StageKind.INGEST: frozenset(),
    StageKind.KB_ENRICH: frozenset(),
    StageKind.MM_SEARCH: frozenset(),
    StageKind.CATALOG: frozenset(),
    StageKind.RETRIEVE: frozenset({StageKind.INGEST, StageKind.KB_ENRICH}),
    StageKind.TICKETMIND: frozenset({StageKind.INGEST, StageKind.KB_ENRICH}),
    StageKind.EVOLVE: frozenset({StageKind.RETRIEVE, StageKind.TICKETMIND, StageKind.MM_SEARCH}),
    StageKind.COEVOLVE: frozenset({StageKind.EVOLVE}),
}

CANONICAL_FULL_RUN: list[StageKind] = [
    StageKind.INGEST,
    StageKind.KB_ENRICH,
    StageKind.MM_SEARCH,
    StageKind.CATALOG,
    StageKind.RETRIEVE,
    StageKind.TICKETMIND,
    StageKind.EVOLVE,
    StageKind.COEVOLVE,
]


@runtime_checkable
class Adapter(Protocol):
    kind: StageKind
    name: str
    version: str

    def validate_inputs(self, inputs: dict[str, Any]) -> None: ...
    def validate_outputs(self, outputs: dict[str, Any]) -> None: ...
    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]: ...


@dataclass(frozen=True)
class Settings:
    """Tunable defaults. All read from env in `metaorch.config.load_settings()`."""

    embed_dim: int = 384
    top_k_default: int = 5
    tau_default: float = 0.01
    weight_w_default: float = 1.5
    catalog_min_delta: float = 2.0
    evolve_max_rounds: int = 7
    rgqm_budget: int = 80
    rgqm_checkpoint: int = 30
    api_host: str = "127.0.0.1"
    api_port: int = 8000


def load_settings() -> Settings:
    import os

    def _env(name: str, cast: type, default: Any) -> Any:
        raw = os.environ.get(name)
        if raw is None or raw == "":
            return default
        if cast is bool:
            return raw.lower() in {"1", "true", "yes", "on"}
        return cast(raw)

    return Settings(
        embed_dim=_env("METAORCH_EMBED_DIM", int, 384),
        top_k_default=_env("METAORCH_TOP_K", int, 5),
        tau_default=_env("METAORCH_TAU", float, 0.01),
        weight_w_default=_env("METAORCH_WEIGHT_W", float, 1.5),
        catalog_min_delta=_env("METAORCH_CATALOG_MIN_DELTA", float, 2.0),
        evolve_max_rounds=_env("METAORCH_EVOLVE_MAX_ROUNDS", int, 7),
        rgqm_budget=_env("METAORCH_RGQM_BUDGET", int, 80),
        rgqm_checkpoint=_env("METAORCH_RGQM_CHECKPOINT", int, 30),
        api_host=os.environ.get("METAORCH_API_HOST", "127.0.0.1"),
        api_port=_env("METAORCH_API_PORT", int, 8000),
    )