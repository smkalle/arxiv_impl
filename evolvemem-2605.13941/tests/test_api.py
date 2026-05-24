"""Tests for the FastAPI application."""
import pytest
from fastapi.testclient import TestClient


def test_health_endpoint():
    from api import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"
        assert "simplemem" in data


def test_diagnose_returns_results():
    from api import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/diagnose", json={"ticket_text": "app crash on login"})
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert "latency_ms" in data
        assert isinstance(data["results"], list)


def test_diagnose_empty_text():
    from api import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.post("/diagnose", json={"ticket_text": "  "})
        assert r.status_code == 422


def test_loops_endpoint():
    from api import create_app
    app = create_app()
    with TestClient(app) as client:
        r = client.get("/loops")
        assert r.status_code == 200
        data = r.json()
        assert "L1" in data
        assert "L3" in data


def test_metrics_endpoint():
    from api import create_app
    app = create_app()
    with TestClient(app) as client:
        client.post("/diagnose", json={"ticket_text": "billing issue"})
        r = client.get("/metrics")
        assert r.status_code == 200
        data = r.json()
        assert data["total_requests"] >= 1
