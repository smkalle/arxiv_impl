"""
Append-only JSONL failure log shared by all four AutoResearch loops.
Each entry records one round of a loop: the patch attempted, whether it was
accepted, and the fitness before/after.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class FailureLogger:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def log(
        self,
        loop_id: str,           # "L1" | "L2" | "L3" | "L4"
        round_no: int,
        fitness_before: float,
        fitness_after: float,
        action: dict[str, Any],
        diagnosis: str,
        accepted: bool,
        revert_reason: str | None = None,
    ) -> None:
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "loop_id": loop_id,
            "round_no": round_no,
            "fitness_before": round(fitness_before, 6),
            "fitness_after": round(fitness_after, 6),
            "delta": round(fitness_after - fitness_before, 6),
            "action": action,
            "diagnosis_snippet": diagnosis[:300] if diagnosis else "",
            "accepted": accepted,
            "revert_reason": revert_reason,
        }
        with open(self._path, "a") as f:
            f.write(json.dumps(entry) + "\n")

    def read_all(self) -> list[dict[str, Any]]:
        if not self._path.exists():
            return []
        entries = []
        with open(self._path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        return entries

    def read_for_loop(self, loop_id: str) -> list[dict[str, Any]]:
        return [e for e in self.read_all() if e.get("loop_id") == loop_id]
