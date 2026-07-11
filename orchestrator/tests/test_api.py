"""API-layer tests using FastAPI TestClient."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from metaorch import __version__
from metaorch.api.deps import get_executor, get_run_store
from metaorch.api.main import create_app


@pytest.fixture
def client() -> TestClient:
    # Use create_app so we get a fresh app instance per test module.
    return TestClient(create_app())


@pytest.fixture(autouse=True)
def _reset_run_store() -> None:
    get_run_store()._runs.clear()
    yield
    get_run_store()._runs.clear()


def test_health(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["adapters_loaded"] == 8
    assert len(body["stages_available"]) == 8
    assert body["version"] == __version__


def test_pipelines_returns_canonical_dag(client: TestClient) -> None:
    r = client.get("/pipelines")
    assert r.status_code == 200
    body = r.json()
    assert body["name"] == "canonical-full-run"
    assert len(body["stages"]) == 8
    dag = body["dag"]
    assert set(dag["RETRIEVE"]) == {"INGEST", "KB_ENRICH"}
    assert set(dag["EVOLVE"]) == {"RETRIEVE", "TICKETMIND", "MM_SEARCH"}
    assert dag["COEVOLVE"] == ["EVOLVE"]
    assert dag["CATALOG"] == []
    assert dag["INGEST"] == []


def test_list_stages_returns_one_descriptor_per_stage(client: TestClient) -> None:
    r = client.get("/stages")
    assert r.status_code == 200
    stages = r.json()
    assert len(stages) == 8
    kinds = {s["kind"] for s in stages}
    assert kinds == {
        "INGEST", "KB_ENRICH", "MM_SEARCH", "CATALOG",
        "RETRIEVE", "TICKETMIND", "EVOLVE", "COEVOLVE",
    }
    for s in stages:
        assert s["adapter_name"]
        assert s["adapter_version"]
        assert isinstance(s["input_keys"], list) and s["input_keys"]
        assert isinstance(s["output_keys"], list) and s["output_keys"]


def test_post_runs_with_empty_body_runs_full_pipeline(client: TestClient) -> None:
    r = client.post("/runs", json={})
    assert r.status_code == 200, r.text
    body = r.json()
    run = body["run"]
    assert run["status"] == "completed", run["stage_results"]
    assert len(run["stage_results"]) == 8
    for sr in run["stage_results"]:
        assert sr["provenance"]["status"] == "ok"


def test_post_runs_then_get_run_by_id(client: TestClient) -> None:
    r = client.post("/runs", json={})
    assert r.status_code == 200
    run_id = r.json()["run"]["run_id"]
    r2 = client.get(f"/runs/{run_id}")
    assert r2.status_code == 200
    assert r2.json()["run"]["run_id"] == run_id


def test_get_run_404_for_unknown_id(client: TestClient) -> None:
    r = client.get("/runs/does-not-exist")
    assert r.status_code == 404


def test_post_runs_with_dry_run_catalog_config(client: TestClient) -> None:
    # Override the CATALOG stage config so dry_run=True; assert manifests_committed==0.
    req = {
        "plan": {
            "stages": ["CATALOG"],
            "stage_configs": {"CATALOG": {"dry_run": True}},
            "resume_from": None,
        },
        "context": {"sku_ids": ["A", "B"], "sources": ["gs1"]},
    }
    r = client.post("/runs", json=req)
    assert r.status_code == 200, r.text
    stages = r.json()["run"]["stage_results"]
    assert len(stages) == 1
    assert stages[0]["stage"] == "CATALOG"
    assert stages[0]["artifacts"]["manifests_committed"] == 0
    assert stages[0]["artifacts"]["avg_score_delta"] is None


def test_post_runs_resume_from_co_evolve_skips_all_upstream(client: TestClient) -> None:
    req = {
        "plan": {
            "stages": ["INGEST", "KB_ENRICH", "MM_SEARCH", "CATALOG",
                       "RETRIEVE", "TICKETMIND", "EVOLVE", "COEVOLVE"],
            "stage_configs": {},
            "resume_from": "COEVOLVE",
        },
        "context": {},
    }
    r = client.post("/runs", json=req)
    assert r.status_code == 200, r.text
    stages = r.json()["run"]["stage_results"]
    by_stage = {s["stage"]: s for s in stages}
    # COEVOLVE's transitive hard deps all skipped.
    for s in ("INGEST", "KB_ENRICH", "MM_SEARCH", "RETRIEVE", "TICKETMIND", "EVOLVE"):
        assert by_stage[s]["provenance"]["status"] == "skipped", s
    assert by_stage["COEVOLVE"]["provenance"]["status"] == "ok"
    # CATALOG is not a transitive dep of COEVOLVE, so it executes.
    assert by_stage["CATALOG"]["provenance"]["status"] == "ok"


def test_post_runs_rejects_invalid_plan(client: TestClient) -> None:
    req = {
        "plan": {
            "stages": ["RETRIEVE"],  # missing INGEST + KB_ENRICH deps
            "stage_configs": {},
            "resume_from": None,
        },
        "context": {},
    }
    r = client.post("/runs", json=req)
    assert r.status_code == 422