"""L1 editor — applies patches to DevSetConfig."""
from __future__ import annotations

import dataclasses
from typing import Any

from dev_set import DevSetConfig


class L1Editor:
    VALID_KEYS = {f.name for f in dataclasses.fields(DevSetConfig)}
    CONSTRAINTS = {
        "min_csat": (1, 5),
        "n_train": (50, 200),
        "vocab_gap_ratio": (0.0, 0.5),
    }

    def apply(self, config: DevSetConfig, patch: dict[str, Any]) -> DevSetConfig:
        clean: dict[str, Any] = {}
        for k, v in patch.items():
            if k not in self.VALID_KEYS:
                continue
            if k in self.CONSTRAINTS:
                lo, hi = self.CONSTRAINTS[k]
                v = max(lo, min(hi, v))
            clean[k] = v
        if not clean:
            return config
        return dataclasses.replace(config, **clean)

    def revert(self, config: DevSetConfig, prev: DevSetConfig) -> DevSetConfig:
        return prev
