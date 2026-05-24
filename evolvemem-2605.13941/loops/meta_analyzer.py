"""
MetaAnalyzer — shared guard for all four AutoResearch loops.

Three decisions per round:
  accept  — fitness improved; adopt the patch
  revert  — fitness regressed; undo the patch
  reject  — no improvement; undo and continue
  explore — fitness flat for plateau_patience rounds; signal LLM to try something novel
"""
from __future__ import annotations


class MetaAnalyzer:
    def __init__(
        self,
        min_delta: float = 1e-4,
        plateau_patience: int = 2,
    ) -> None:
        self._min_delta = min_delta
        self._plateau_patience = plateau_patience
        self._flat_rounds = 0
        self._best_fitness = float("-inf")

    def evaluate(
        self,
        fitness_before: float,
        fitness_after: float,
    ) -> tuple[str, str | None]:
        """
        Returns (decision, reason).
        decision: "accept" | "revert" | "reject" | "explore"
        """
        delta = fitness_after - fitness_before

        if delta >= self._min_delta:
            self._flat_rounds = 0
            self._best_fitness = max(self._best_fitness, fitness_after)
            return "accept", None

        if delta < 0:
            # Regression — revert unconditionally
            return "revert", f"fitness regressed by {abs(delta):.6f}"

        # delta in [0, min_delta) — no meaningful improvement
        self._flat_rounds += 1
        if self._flat_rounds >= self._plateau_patience:
            self._flat_rounds = 0
            return "explore", (
                f"plateau: {self._plateau_patience} flat rounds "
                f"(delta={delta:.6f})"
            )
        return "reject", f"no improvement (delta={delta:.6f})"

    def reset(self) -> None:
        self._flat_rounds = 0
        self._best_fitness = float("-inf")

    @property
    def stagnating(self) -> bool:
        return self._flat_rounds >= self._plateau_patience - 1
