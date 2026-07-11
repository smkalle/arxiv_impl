"""EVOLVE — EvolveMem AutoResearch contract: 4-loop retrieval config evolution."""

from __future__ import annotations

from typing import Any

from metaorch.adapters.base import (
    _require_float,
    _require_int,
    _require_keys,
    _require_list,
    _require_str,
)
from metaorch.errors import ContractError
from metaorch.models import StageKind

_VALID_LOOPS = ("L1", "L2", "L3", "L4")


class EvolvememAdapter:
    kind = StageKind.EVOLVE
    name = "evolvemem-auto-research"
    version = "0.1.0"

    def validate_inputs(self, inputs: dict[str, Any]) -> None:
        where = "EVOLVE.validate_inputs"
        _require_keys(inputs, ("start_from", "baseline_f1", "max_rounds"), where)
        _require_str(inputs, "start_from", where, allowed=_VALID_LOOPS)
        _require_float(inputs, "baseline_f1", where, min_value=0.0)
        _require_int(inputs, "max_rounds", where, min_value=1)
        if "only" in inputs and inputs["only"] is not None:
            if not isinstance(inputs["only"], str) or inputs["only"] not in _VALID_LOOPS:
                raise ContractError(f"{where}: 'only' must be one of {_VALID_LOOPS} or None")

    def validate_outputs(self, outputs: dict[str, Any]) -> None:
        where = "EVOLVE.validate_outputs"
        _require_keys(outputs, ("loop_results", "final_config_version", "fitness_gain"), where)
        _require_list(outputs, "loop_results", where)
        _require_str(outputs, "final_config_version", where, allowed=("baseline", "evolved"))
        _require_float(outputs, "fitness_gain", where, min_value=0.0)
        if outputs["final_config_version"] == "evolved":
            has_patch = any(
                lr.get("accepted_patches") for lr in outputs["loop_results"]
                if isinstance(lr, dict) and isinstance(lr.get("accepted_patches"), list)
            )
            if not has_patch:
                raise ContractError(
                    f"{where}: final_config_version=evolved requires >=1 accepted_patches entry"
                )
        for i, lr in enumerate(outputs["loop_results"]):
            if not isinstance(lr, dict):
                raise ContractError(f"{where}: loop_results[{i}] must be dict")
            for k in ("loop_id", "rounds_run", "baseline_fitness", "best_fitness",
                      "accepted_patches", "discovered_dimensions"):
                if k not in lr:
                    raise ContractError(f"{where}: loop_results[{i}] missing '{k}'")

    def run(self, inputs: dict[str, Any], config: dict[str, Any]) -> dict[str, Any]:
        start = inputs["start_from"]
        only = inputs.get("only")
        base = inputs["baseline_f1"]
        max_rounds = inputs["max_rounds"]

        order = [only] if only else list(_VALID_LOOPS[_VALID_LOOPS.index(start):])
        # Deterministic "evolution": each loop improves fitness by 0.05.
        gain_per_loop = 0.05
        loop_results = []
        cur_fitness = base
        any_patch = False
        for i, loop in enumerate(order):
            rounds = min(max_rounds, 3)
            new_fitness = round(min(cur_fitness + gain_per_loop, 0.95), 4)
            patches = (
                [f"patch:{loop}:top_k={5 + i}"] if i > 0 else []
            )
            dims = [f"top_k_{loop}", f"fusion_weight_{loop}"]
            any_patch = any_patch or bool(patches)
            loop_results.append(
                {
                    "loop_id": loop,
                    "rounds_run": rounds,
                    "baseline_fitness": cur_fitness,
                    "best_fitness": new_fitness,
                    "accepted_patches": patches,
                    "discovered_dimensions": dims,
                }
            )
            cur_fitness = new_fitness

        evolved = any_patch
        return {
            "loop_results": loop_results,
            "final_config_version": "evolved" if evolved else "baseline",
            "fitness_gain": round(cur_fitness - base, 4),
        }