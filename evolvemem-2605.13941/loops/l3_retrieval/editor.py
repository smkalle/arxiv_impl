"""L3 editor — applies patches to RetrievalConfig (open-schema)."""
from __future__ import annotations

from typing import Any

from loops.action_space import RetrievalConfig


_KNOWN_CONSTRAINTS: dict[str, tuple] = {
    "top_k":            (1, 20, int),
    "bm25_weight":      (0.1, 3.0, float),
    "semantic_weight":  (0.0, 2.0, float),
    "symbolic_weight":  (0.0, 1.0, float),
    "tau":              (0.001, 0.5, float),
}


class L3Editor:
    def apply(
        self,
        config: RetrievalConfig,
        patch: dict[str, Any],
    ) -> tuple[RetrievalConfig, list[str]]:
        """
        Apply patch to config.
        Returns (new_config, newly_discovered_dimension_names).
        """
        known = {
            f.name
            for f in __import__("dataclasses").fields(config)
            if not f.name.startswith("_")
        }
        new_dims: list[str] = []

        # Clamp known numeric fields
        clean: dict[str, Any] = {}
        for k, v in patch.items():
            if k.startswith("__"):
                continue
            if k in _KNOWN_CONSTRAINTS:
                lo, hi, typ = _KNOWN_CONSTRAINTS[k]
                v = typ(max(lo, min(hi, float(v))))
            if k not in known and k not in config._extras:
                new_dims.append(k)
            clean[k] = v

        new_config = config.apply_patch(clean)
        return new_config, new_dims

    def revert(self, prev: RetrievalConfig) -> RetrievalConfig:
        return prev
