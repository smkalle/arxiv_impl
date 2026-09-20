"""Point every path at a temp directory so the suite never touches the checkout."""

from __future__ import annotations

from pathlib import Path

import pytest

from leafcx import config


@pytest.fixture(autouse=True)
def isolated_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(config, "WORKSPACE", tmp_path / "workspace")
    monkeypatch.setattr(config, "HIDDEN_TESTS", tmp_path / "hidden_tests")
    monkeypatch.setattr(config, "TASKS_DIR", tmp_path / "tasks")
    monkeypatch.setattr(config, "RUNS_DIR", tmp_path / "runs")
    return tmp_path


@pytest.fixture
def workspace(isolated_paths: Path) -> Path:
    root = isolated_paths / "workspace"
    root.mkdir(parents=True, exist_ok=True)
    return root
