"""Serialization, determinism, idempotency, and concurrency tests."""

from __future__ import annotations

import json
import subprocess
import sys
import concurrent.futures
from pathlib import Path
from typing import Any

import pytest

from fastapi.testclient import TestClient

from metaorch.adapters import default_adapters
from metaorch.api.deps import get_executor, get_run_store
from metaorch.api.main import create_app
from metaorch.executor import PipelineExecutor
from metaorch.models import PipelineContext, RunPlan, StageKind
from metaorch.pipeline import canonical_full_run_plan, default_context


# --- Serialization round-trips -------------------------------------------

@pytest.mark.parametrize("model_name", [
    "StageKind", "Provenance", "StageResult", "RunPlan", "PipelineRun", "PipelineContext",
])
def test_pydantic_models_roundtrip_json(model_name: str) -> None:
    from metaorch.models import (
        StageKind as _SK, Provenance as _P, StageResult as _SR,
        RunPlan as _RP, PipelineRun as _PR, PipelineContext as _PC,
    )
    table = {
        "StageKind": _SK,
        "Provenance": _P,
        "StageResult": _SR,
        "RunPlan": _RP,
        "PipelineRun": _PR,
        "PipelineContext": _PC,
    }
    cls = table[model_name]
    if cls is _SK:
        for v in _SK:
            assert _SK(v.value) is v
        return
    run = PipelineExecutor().execute(canonical_full_run_plan(), default_context())
    instance_table = {
        _PR: run,
        _SR: run.stage_results[0],
        _P: run.stage_results[0].provenance,
        _RP: run.plan,
        _PC: default_context(),
    }
    instance = instance_table[cls]
    s = instance.model_dump_json()
    restored = cls.model_validate_json(s)
    assert restored == instance, f"{model_name} round-trip mismatch"


def test_run_serializes_to_clean_json() -> None:
    """The full PipelineRun must JSON-serialize without custom encoders crashing."""
    run = PipelineExecutor().execute(canonical_full_run_plan(), default_context())
    s = run.model_dump_json()
    parsed = json.loads(s)
    assert parsed["status"] == "completed"
    assert parsed["run_id"] == run.run_id
    # Every stage's provenance survives with non-empty adapter name.
    for sr in parsed["stage_results"]:
        assert sr["provenance"]["adapter"]
        assert sr["provenance"]["status"] in ("ok", "skipped", "failed")


# --- Determinism ----------------------------------------------------------

def test_full_run_deterministic_stage_ids_and_shapes() -> None:
    """Two consecutive full runs produce the same stage_results shapes (ids differ; outputs match)."""
    ctx = default_context()
    run1 = PipelineExecutor().execute(canonical_full_run_plan(), ctx)
    run2 = PipelineExecutor().execute(canonical_full_run_plan(), ctx)
    assert run1.run_id != run2.run_id  # UUIDs differ
    assert len(run1.stage_results) == len(run2.stage_results)
    for r1, r2 in zip(run1.stage_results, run2.stage_results):
        assert r1.stage == r2.stage
        # same adapter config -> same artifact *shape* (counts not exact equality of latencies).
        assert set(r1.artifacts.keys()) == set(r2.artifacts.keys())


def test_co_evolve_deterministic_token_count_for_same_budget() -> None:
    adapter = default_adapters()[StageKind.COEVOLVE]
    out1 = adapter.run({"mode": "rqgm", "budget": 80, "checkpoint": 30,
                         "task_set": "tasks/humaneval_20.json"}, {})
    out2 = adapter.run({"mode": "rqgm", "budget": 80, "checkpoint": 30,
                         "task_set": "tasks/humaneval_20.json"}, {})
    assert out1["blended_tokens"] == out2["blended_tokens"]
    assert out1["baseline_tokens"] == out2["baseline_tokens"]


# --- Idempotency ---------------------------------------------------------

def test_run_store_get_returns_equivalent_run() -> None:
    """get(put(run)) returns a run equal to the original."""
    get_run_store()._runs.clear()
    run = PipelineExecutor().execute(canonical_full_run_plan(), default_context())
    get_run_store().put(run)
    fetched = get_run_store().get(run.run_id)
    assert fetched is not None
    assert fetched.run_id == run.run_id
    assert fetched.status == run.status
    assert len(fetched.stage_results) == len(run.stage_results)


def test_run_store_get_returns_none_for_unknown_id() -> None:
    get_run_store()._runs.clear()
    assert get_run_store().get("nonexistent") is None


def test_post_runs_twice_yields_distinct_run_ids_via_api() -> None:
    get_run_store()._runs.clear()
    c = TestClient(create_app())
    r1 = c.post("/runs", json={})
    r2 = c.post("/runs", json={})
    assert r1.status_code == 200 and r2.status_code == 200
    assert r1.json()["run"]["run_id"] != r2.json()["run"]["run_id"]


# --- Concurrency ----------------------------------------------------------

def test_post_runs_concurrent_20_parallel_all_succeed() -> None:
    get_run_store()._runs.clear()
    c = TestClient(create_app())
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        futures = [pool.submit(c.post, "/runs", json={}) for _ in range(20)]
        results = [f.result() for f in futures]
    statuses = sorted({r.status_code for r in results})
    assert statuses == [200], f"unexpected codes: {statuses}"
    run_ids = {r.json()["run"]["run_id"] for r in results}
    # All 20 run_ids distinct — no race-induced overwrite.
    assert len(run_ids) == 20


def test_executor_serial_10_runs_no_cross_contamination_of_artifacts() -> None:
    ex = PipelineExecutor()
    for _ in range(10):
        run = ex.execute(canonical_full_run_plan(), default_context())
        assert run.status == "completed"
        assert {r.stage for r in run.stage_results} == set(canonical_full_run_plan().stages)


# --- Empty / boundary user payloads via API ------------------------------

def test_post_runs_with_empty_context_runs_default_context() -> None:
    get_run_store()._runs.clear()
    c = TestClient(create_app())
    r = c.post("/runs", json={"context": {}})
    assert r.status_code == 200, r.text
    assert r.json()["run"]["status"] == "completed"


def test_post_runs_with_only_ticket_text_keeps_default_kb() -> None:
    """Regression: previously this failed because user context dropped default kb_articles."""
    get_run_store()._runs.clear()
    c = TestClient(create_app())
    r = c.post("/runs", json={"context": {"ticket_text": "reset MFA identity authenticator"}})
    assert r.status_code == 200, r.text
    run = r.json()["run"]
    assert run["status"] == "completed", run["stage_results"]
    kb_stage = next(s for s in run["stage_results"] if s["stage"] == "KB_ENRICH")
    assert kb_stage["provenance"]["status"] == "ok"


def test_post_runs_with_only_sku_ids_keeps_default_ticket() -> None:
    get_run_store()._runs.clear()
    c = TestClient(create_app())
    r = c.post("/runs", json={"context": {"sku_ids": ["X-1", "X-2"], "sources": ["gs1"]}})
    assert r.status_code == 200, r.text
    run = r.json()["run"]
    assert run["status"] == "completed"
    retrieve = next(s for s in run["stage_results"] if s["stage"] == "RETRIEVE")
    assert retrieve["provenance"]["status"] == "ok"


# --- Live subprocess uvicorn integration ---------------------------------

def test_live_subprocess_uvicorn_serves_run() -> None:
    """Boot a real uvicorn, hit /runs, tear down — full ASGI integration beyond TestClient."""
    import httpx
    import os
    import socket
    import time

    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()

    cwd = Path(__file__).resolve().parent.parent
    env = {**os.environ, "PYTHONPATH": str(cwd)}
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "metaorch.api.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(cwd), env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        base = f"http://127.0.0.1:{port}"
        deadline = time.time() + 8.0
        ready = False
        while time.time() < deadline:
            try:
                with httpx.Client(base_url=base, timeout=0.5) as c:
                    if c.get("/health").status_code == 200:
                        ready = True
                        break
            except httpx.HTTPError:
                pass
            time.sleep(0.15)
        assert ready, "uvicorn did not boot in 8s"

        with httpx.Client(base_url=base, timeout=10.0) as c:
            r = c.post("/runs", json={})
            assert r.status_code == 200
            run = r.json()["run"]
            assert run["status"] == "completed"
            assert len(run["stage_results"]) == 8
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait(timeout=5)