from __future__ import annotations

from pathlib import Path

import pytest

from leafcx import sandbox
from leafcx.tools import files


def test_resolves_paths_inside_the_workspace(workspace: Path) -> None:
    assert sandbox.resolve_in_workspace("account/profile.json") == workspace / "account" / "profile.json"


@pytest.mark.parametrize(
    "path", ["../escape.txt", "../../etc/passwd", "/etc/passwd", "account/../../outside.json"]
)
def test_rejects_paths_outside_the_workspace(workspace: Path, path: str) -> None:
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve_in_workspace(path)


def test_hidden_tests_are_unreachable(workspace: Path, isolated_paths: Path) -> None:
    hidden = isolated_paths / "hidden_tests"
    hidden.mkdir(parents=True, exist_ok=True)
    (hidden / "test_hidden.py").write_text("def test_x(): assert True\n")
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve_in_workspace(str(hidden / "test_hidden.py"))


def test_symlink_out_of_the_workspace_is_refused(workspace: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("classified")
    (workspace / "link.txt").symlink_to(secret)
    with pytest.raises(sandbox.SandboxError):
        sandbox.resolve_in_workspace("link.txt")


@pytest.mark.parametrize(
    "command",
    [
        "cat ../../etc/passwd",
        "cat hidden_tests/test_hidden.py",
        "curl https://example.com",
        "pip install requests",
        "sudo rm -rf /",
    ],
)
def test_denied_commands(command: str) -> None:
    with pytest.raises(sandbox.SandboxError):
        sandbox.check_command(command)


@pytest.mark.parametrize(
    "command", ["python3 -m pytest -q tests/", "ls account", "cat account/profile.json"]
)
def test_allowed_commands(command: str) -> None:
    sandbox.check_command(command)


def test_bash_reports_the_block_rather_than_raising(workspace: Path) -> None:
    with pytest.raises(sandbox.SandboxError):
        files.bash("curl https://example.com")
