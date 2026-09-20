"""The five Leaf tools: read, write, edit, glob, bash.

Kept deliberately close to the paper's harness.  The one detail worth copying
exactly is `edit`: it refuses unless the `old` span matches exactly once.  Small
models otherwise reach for `write` and flatten a file they only meant to touch
in one place.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from .. import sandbox
from ..config import AgentConfig

#: Files larger than this are refused by `read` rather than blowing the context.
MAX_READ_BYTES = 400_000


def read(path: str, offset: int = 1, limit: int = 200) -> str:
    """Read a file with 1-based line numbers."""
    target = sandbox.resolve_in_workspace(path)
    if not target.exists():
        return f"error: no such file: {path}"
    if target.is_dir():
        return f"error: {path} is a directory (use glob)"
    if target.stat().st_size > MAX_READ_BYTES:
        return f"error: {path} is {target.stat().st_size} bytes; read it in slices with bash"
    offset = max(1, int(offset))
    limit = max(1, int(limit))
    lines = target.read_text(errors="replace").splitlines()
    window = lines[offset - 1 : offset - 1 + limit]
    if not window:
        return "(empty)" if not lines else f"(no lines at offset {offset}; file has {len(lines)})"
    body = "\n".join(f"{i + offset:>5}|{line}" for i, line in enumerate(window))
    remaining = len(lines) - (offset - 1 + len(window))
    if remaining > 0:
        body += f"\n... {remaining} more line(s); re-read with offset={offset + len(window)}"
    return body


def write(path: str, content: str) -> str:
    """Create or overwrite a file."""
    target = sandbox.resolve_in_workspace(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content)
    return f"wrote {sandbox.relative(target)} ({len(content)} bytes)"


def edit(path: str, old: str, new: str) -> str:
    """Replace exactly one unique occurrence of `old` with `new`."""
    target = sandbox.resolve_in_workspace(path)
    if not target.exists():
        return f"error: no such file: {path}"
    source = target.read_text()
    occurrences = source.count(old)
    if occurrences == 0:
        return (
            f"edit failed: `old` not found in {path}. "
            "Read the file again and copy the span exactly, whitespace included."
        )
    if occurrences > 1:
        return (
            f"edit failed: `old` matches {occurrences} times in {path}. "
            "Extend it with surrounding lines until it is unique."
        )
    target.write_text(source.replace(old, new, 1))
    return f"edited {sandbox.relative(target)}"


def glob(pattern: str) -> str:
    """Find files by glob pattern under the workspace root."""
    root = sandbox.workspace_root()
    if not root.exists():
        return "(no workspace)"
    hits = sorted(
        sandbox.relative(p)
        for p in root.rglob(pattern)
        if p.is_file() and ".git" not in p.parts and "__pycache__" not in p.parts
    )
    if not hits:
        return "(no matches)"
    shown = hits[:200]
    body = "\n".join(shown)
    if len(hits) > len(shown):
        body += f"\n... {len(hits) - len(shown)} more"
    return body


def bash(command: str, timeout: int | None = None) -> str:
    """Run a shell command inside the workspace."""
    sandbox.check_command(command)
    root = sandbox.workspace_root()
    root.mkdir(parents=True, exist_ok=True)
    timeout = int(timeout or AgentConfig().bash_timeout)
    try:
        completed = subprocess.run(
            command,
            shell=True,
            cwd=str(root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return f"exit=timeout\ncommand exceeded {timeout}s and was killed"
    output = (completed.stdout + completed.stderr)[-8000:]
    return f"exit={completed.returncode}\n{output}".rstrip()


FILE_TOOLS = {
    "read": read,
    "write": write,
    "edit": edit,
    "glob": glob,
    "bash": bash,
}

FILE_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "read",
            "description": "Read a file from the account workspace, with 1-based line numbers.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Workspace-relative path."},
                    "offset": {"type": "integer", "description": "First line to show (default 1)."},
                    "limit": {"type": "integer", "description": "How many lines (default 200)."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write",
            "description": "Create a file, or overwrite it completely. Prefer `edit` for small changes.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "edit",
            "description": (
                "Replace exactly one unique span of text in a file. Fails if `old` "
                "appears zero times or more than once."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "old": {"type": "string", "description": "Exact text to replace; must be unique."},
                    "new": {"type": "string"},
                },
                "required": ["path", "old", "new"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "glob",
            "description": "List workspace files matching a glob pattern, e.g. 'account/*.json'.",
            "parameters": {
                "type": "object",
                "properties": {"pattern": {"type": "string"}},
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "bash",
            "description": (
                "Run a shell command in the workspace. Use it to run the visible checks: "
                "`python3 -m pytest -q tests/`. Network access is disabled."
            ),
            "parameters": {
                "type": "object",
                "properties": {"command": {"type": "string"}},
                "required": ["command"],
            },
        },
    },
]
