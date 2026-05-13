from __future__ import annotations

import asyncio
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from sira_kb_ingestor import IngestAndRetrieveConfig, Retriever, setup_full_system
from sira_kb_ingestor.orchestration import normalize_ollama_host


def _require_real_stack() -> None:
    pytest.importorskip("pyarrow", reason="real integration requires pyarrow")
    pytest.importorskip("faiss", reason="real integration requires faiss")

    host = normalize_ollama_host(os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11435")).rstrip("/")
    try:
        with urllib.request.urlopen(f"{host}/api/tags", timeout=2) as response:
            response.read()
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        pytest.skip(f"real integration requires a reachable Ollama service at {host}: {exc}")


def _write_kb(path: Path) -> None:
    current = "2026-05-01T00:00:00+00:00"
    path.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "article_id": "KB-AUTH",
                        "title": "Login failures",
                        "body": "Clear authentication cookies and reset password when login fails.",
                        "enriched_terms": ["sign in broken", "password loop"],
                        "last_updated": current,
                        "enriched_at": current,
                    }
                ),
                json.dumps(
                    {
                        "article_id": "KB-BILLING",
                        "title": "Invoice download",
                        "body": "Regenerate billing invoices from account settings.",
                        "enriched_terms": ["receipt missing"],
                        "last_updated": current,
                        "enriched_at": current,
                    }
                ),
            ]
        )
        + "\n",
        encoding="utf-8",
    )


def _assert_artifacts(out: Path) -> None:
    for name in ["tickets.arrow", "ticket_index.faiss", "enriched_kb.jsonl", "kb_index.pkl", "setup_summary.json"]:
        assert (out / name).exists(), f"missing artifact {name}"


def _assert_query_shape(out: Path) -> None:
    response = Retriever(out).retrieve("login fails", top_k=1)
    assert set(response) == {"kb_articles", "audit"}
    assert isinstance(response["kb_articles"], list)
    if response["kb_articles"]:
        assert {"id", "title", "body", "score"}.issubset(response["kb_articles"][0])
    assert "fallback_used" in response["audit"]


def test_real_e2e_setup_zendesk_csv(tmp_path: Path) -> None:
    print("[INTEGRATION] Running real setup flow with Zendesk CSV input")
    _require_real_stack()
    tickets = tmp_path / "zendesk.csv"
    tickets.write_text(
        "id,subject,description,status,created_at,tags\n"
        "1,Login broken,Cannot sign in to the mobile app,open,2026-05-01T00:00:00,auth\n"
        "2,Invoice missing,Need a receipt for last month,open,2026-05-01T00:00:00,billing\n",
        encoding="utf-8",
    )
    kb = tmp_path / "kb.jsonl"
    _write_kb(kb)
    out = tmp_path / "out-zendesk"

    asyncio.run(setup_full_system(tickets, kb, IngestAndRetrieveConfig(output_path=out, batch_size=2, max_workers=1)))

    _assert_artifacts(out)
    _assert_query_shape(out)


def test_real_e2e_setup_jira_json(tmp_path: Path) -> None:
    print("[INTEGRATION] Running real setup flow with Jira JSON input")
    _require_real_stack()
    tickets = tmp_path / "jira.json"
    rows = [
        {
            "key": "SUP-1",
            "fields": {
                "summary": "Login broken",
                "description": "Cannot sign in to the mobile app",
                "status": {"name": "Open"},
                "created": "2026-05-01T00:00:00",
                "labels": ["auth"],
            },
        },
        {
            "key": "SUP-2",
            "fields": {
                "summary": "Invoice missing",
                "description": "Need a receipt for last month",
                "status": {"name": "Open"},
                "created": "2026-05-01T00:00:00",
                "labels": ["billing"],
            },
        },
    ]
    tickets.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    kb = tmp_path / "kb.jsonl"
    _write_kb(kb)
    out = tmp_path / "out-jira"

    asyncio.run(setup_full_system(tickets, kb, IngestAndRetrieveConfig(output_path=out, batch_size=2, max_workers=1)))

    _assert_artifacts(out)
    _assert_query_shape(out)
