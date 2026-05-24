"""L4 editor — applies a new diagnosis prompt string."""
from __future__ import annotations

from pathlib import Path


class L4Editor:
    def apply(self, current_prompt: str, new_prompt: str) -> str:
        """Validate and return the new prompt."""
        new_prompt = new_prompt.strip()
        # Minimal sanity check — reject if suspiciously short
        if len(new_prompt) < 100:
            return current_prompt
        return new_prompt

    def revert(self, prev_prompt: str) -> str:
        return prev_prompt

    def persist(self, prompt: str, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(prompt)
