"""Workspace confinement for the agent's tools.

Honest scoping: the paper's agent ran with an unrestricted shell inside Docker.
Termux has no Docker, so this is a *best-effort* confinement built from path
resolution plus a command denylist — good enough to stop a confused 4B model
from wandering out of the workspace or editing its own grader, and not a
security boundary against an adversary.  Run untrusted policies in a throwaway
container or user account.
"""

from __future__ import annotations

import re
from pathlib import Path

from .config import HIDDEN_TESTS, WORKSPACE


class SandboxError(ValueError):
    """Raised when a tool call tries to leave the workspace."""


#: Shell constructs refused outright.  The first three protect the grader and
#: the filesystem; the rest keep episodes offline and reproducible.
DENIED_COMMAND_PATTERNS: tuple[tuple[str, str], ...] = (
    (r"hidden_tests", "the hidden tests are not visible to the agent"),
    (r"(^|[^\w])\.\.(/|$)", "parent-directory traversal is not allowed"),
    (r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f?\s+/(?!\w*home/user)", "refusing a recursive delete outside the workspace"),
    (r"\b(curl|wget|nc|ncat|telnet|ssh|scp|rsync)\b", "network access is disabled during episodes"),
    (r"\bpip3?\s+install\b", "installing packages during an episode is not allowed"),
    (r"\bsudo\b", "privilege escalation is not available"),
    (r"\b(shutdown|reboot|mkfs|dd\s+if=)\b", "system-level command refused"),
)

_COMPILED = tuple((re.compile(pattern), reason) for pattern, reason in DENIED_COMMAND_PATTERNS)


def workspace_root() -> Path:
    """The live workspace root, re-read each call so tests can relocate it."""
    from . import config  # late import: tests monkeypatch config.WORKSPACE

    return Path(config.WORKSPACE)


def hidden_tests_root() -> Path:
    from . import config

    return Path(config.HIDDEN_TESTS)


def resolve_in_workspace(relative_path: str) -> Path:
    """Resolve `relative_path` under the workspace, or raise `SandboxError`.

    Absolute paths, `..` segments and symlinks that point outside are all
    rejected.  The path itself need not exist yet (callers create files).
    """
    root = workspace_root().resolve()
    candidate = Path(relative_path)
    if candidate.is_absolute():
        target = candidate.resolve()
    else:
        target = (root / candidate).resolve()

    if target != root and root not in target.parents:
        raise SandboxError(f"path escapes the workspace: {relative_path}")

    hidden = hidden_tests_root().resolve()
    if target == hidden or hidden in target.parents:
        raise SandboxError("the hidden tests are not accessible")
    return target


def check_command(command: str) -> None:
    """Raise `SandboxError` if `command` matches the denylist."""
    for pattern, reason in _COMPILED:
        if pattern.search(command):
            raise SandboxError(f"blocked by sandbox: {reason}")


def relative(path: Path) -> str:
    """Workspace-relative display form, for tool output."""
    root = workspace_root().resolve()
    try:
        return str(path.resolve().relative_to(root))
    except ValueError:
        return str(path)


__all__ = [
    "HIDDEN_TESTS",
    "WORKSPACE",
    "SandboxError",
    "check_command",
    "hidden_tests_root",
    "relative",
    "resolve_in_workspace",
    "workspace_root",
]
