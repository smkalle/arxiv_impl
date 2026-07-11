from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from src.evolution import run_evolution
from src.index import build_and_save
from src.session_store import end_session, record_event, start_session
from src.ticket_api import app as api_app
from src.enrich_ui import app as ui_app


def test_api_query_and_health(tiny_corpus, tmp_path, monkeypatch) -> None:
    build_and_save(tiny_corpus, Path("data/bm25_index.pkl"))
    client = TestClient(api_app)

    health = client.get("/health")
    response = client.post("/query", json={"ticket": "login crash", "use_evolved": False})

    assert health.status_code == 200
    assert response.status_code == 200
    assert response.json()["results"][0]["id"]
    assert "latency_ms" in response.json()


def test_session_store_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "sessions.json"
    session = start_session("cust-1", path=path)
    event = record_event(session["session_id"], "first ticket", path=path)
    ended = end_session(session["session_id"], path=path)

    assert event["text"] == "first ticket"
    assert ended["ended_at"]


def test_evolution_writes_state(tmp_path: Path) -> None:
    state = run_evolution(state_path=tmp_path / "state.json", config_path=tmp_path / "config.json")

    assert state["history"]
    assert state["relative_gain"] >= 0.15


def test_dashboard_pages_render() -> None:
    client = TestClient(ui_app)

    assert "Query Inspector" in client.get("/").text
    assert "KB Browser" in client.get("/kb").text
    assert "Evolution Monitor" in client.get("/evolution").text
    assert "System Health" in client.get("/system").text
