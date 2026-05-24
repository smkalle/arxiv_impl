"""
Open-schema RetrievalConfig — the evolving object for the L3 loop.

Known fields have typed defaults. Unknown keys from LLM patches are stored in
_extras and survive serialisation. This is the open-schema mechanism that lets
L3 discover new retrieval dimensions without code changes.
"""
from __future__ import annotations

import dataclasses
import json
from pathlib import Path
from typing import Any


@dataclasses.dataclass
class RetrievalConfig:
    # ── Named fields (L3 may patch any of these) ────────────────────────────
    top_k: int = 5
    bm25_weight: float = 1.0
    semantic_weight: float = 0.5
    symbolic_weight: float = 0.2
    tau: float = 0.01                  # DF filter threshold
    rerank: bool = False
    query_expansion: bool = False

    # ── Open-schema overflow (never serialise directly) ──────────────────────
    _extras: dict[str, Any] = dataclasses.field(
        default_factory=dict, repr=False, compare=False
    )

    # ── Patch API ────────────────────────────────────────────────────────────

    def apply_patch(self, patch: dict[str, Any]) -> "RetrievalConfig":
        """Return a new RetrievalConfig with patch applied (immutable update).

        Known field names → set as typed attributes.
        Unknown keys → stored in _extras (open-schema discovery).
        """
        known = {f.name for f in dataclasses.fields(self) if not f.name.startswith("_")}
        new_extras = dict(self._extras)
        kwargs: dict[str, Any] = {}

        for k, v in patch.items():
            if k.startswith("__"):   # meta-keys like __round, __rationale
                continue
            if k in known:
                # Basic type coercion for LLM output strings
                field_type = next(
                    f.type for f in dataclasses.fields(self) if f.name == k
                )
                kwargs[k] = _coerce(v, field_type)
            else:
                new_extras[k] = v

        new = dataclasses.replace(self, **kwargs)
        object.__setattr__(new, "_extras", new_extras)
        return new

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        d = {
            f.name: getattr(self, f.name)
            for f in dataclasses.fields(self)
            if not f.name.startswith("_")
        }
        d.update(self._extras)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RetrievalConfig":
        known = {f.name for f in dataclasses.fields(cls) if not f.name.startswith("_")}
        kwargs = {k: v for k, v in d.items() if k in known}
        extras = {k: v for k, v in d.items() if k not in known}
        obj = cls(**kwargs)
        object.__setattr__(obj, "_extras", extras)
        return obj

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2))

    @classmethod
    def load(cls, path: Path) -> "RetrievalConfig":
        return cls.from_dict(json.loads(path.read_text()))

    # ── Discovered dimensions helper ─────────────────────────────────────────

    def discovered_dimensions(self) -> list[str]:
        """Return extra keys introduced beyond the baseline field set."""
        return list(self._extras.keys())


def _coerce(value: Any, type_hint: Any) -> Any:
    """Best-effort type coercion for LLM-supplied values."""
    try:
        if type_hint in (int, "int"):
            return int(value)
        if type_hint in (float, "float"):
            return float(value)
        if type_hint in (bool, "bool"):
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)
    except (ValueError, TypeError):
        pass
    return value
