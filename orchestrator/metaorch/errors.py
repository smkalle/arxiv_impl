"""Error types for the metaorch pipeline."""

from __future__ import annotations


class MetaorchError(Exception):
    """Base error for all metaorch failures."""


class ContractError(MetaorchError):
    """Raised by an adapter when inputs or outputs violate the documented contract."""


class AdapterError(MetaorchError):
    """Raised when an adapter fails to run (runtime, not contract, failure)."""


class StageFailed(MetaorchError):
    """Raised/recorded when a stage failed validation or execution."""

    def __init__(self, stage: str, reason: str) -> None:
        super().__init__(f"stage {stage} failed: {reason}")
        self.stage = stage
        self.reason = reason


class MissingAdapter(MetaorchError):
    """Raised when the executor cannot find an adapter for a requested stage."""

    def __init__(self, stage: str) -> None:
        super().__init__(f"no adapter registered for stage {stage}")
        self.stage = stage


class CyclicDag(MetaorchError):
    """Raised when the declared DAG has a cycle."""


class PlanValidationError(MetaorchError):
    """Raised when a RunPlan is structurally invalid (missing hard deps, unknown stage, ...)."""