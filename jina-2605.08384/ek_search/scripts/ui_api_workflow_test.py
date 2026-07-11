"""API integration workflow for validating the dashboard behavior.

Run from ek_search/ while the FastAPI app is running:
    python3 scripts/ui_api_workflow_test.py

Optional environment variables:
    BASE_URL=http://127.0.0.1:8000
    SAMPLE_PATH=./data/samples
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


BASE_URL = os.getenv("BASE_URL", "http://127.0.0.1:8000").rstrip("/")
SAMPLE_PATH = os.getenv("SAMPLE_PATH", "./data/samples")
TIMEOUT_SECONDS = 60
REQUIRE_SEMANTIC_MATCH = os.getenv("REQUIRE_SEMANTIC_MATCH", "0") == "1"


@dataclass
class StepResult:
    name: str
    passed: bool
    details: str


results: list[StepResult] = []


def log(message: str) -> None:
    print(message, flush=True)


def record(name: str, passed: bool, details: str) -> None:
    status = "PASS" if passed else "FAIL"
    log(f"[{status}] {name}: {details}")
    results.append(StepResult(name, passed, details))


def request(method: str, path: str, body: dict[str, Any] | None = None) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    payload = None
    headers = {"Accept": "application/json"}
    if body is not None:
        payload = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"

    req = urllib.request.Request(url, data=payload, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            content_type = resp.headers.get("content-type", "")
            if "application/json" in content_type:
                return resp.status, json.loads(raw)
            return resp.status, raw
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return exc.code, json.loads(raw)
        except json.JSONDecodeError:
            return exc.code, raw


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def step_dashboard_loads() -> None:
    status, body = request("GET", "/")
    assert_true(status == 200, f"expected 200, got {status}")
    assert_true(isinstance(body, str) and "<html" in body.lower(), "response is not HTML")
    record("Dashboard loads", True, "GET / returned HTML")


def step_health() -> dict[str, Any]:
    status, data = request("GET", "/health")
    assert_true(status == 200, f"expected 200, got {status}")
    assert_true(data.get("status") == "ok", f"unexpected health payload: {data}")
    assert_true("backend" in data, "missing backend")
    assert_true("document_count" in data, "missing document_count")
    record(
        "Health check",
        True,
        f"backend={data.get('backend')} dim={data.get('embed_dim')} docs={data.get('document_count')}",
    )
    return data


def step_initial_stats() -> dict[str, Any]:
    status, data = request("GET", "/stats")
    assert_true(status == 200, f"expected 200, got {status}")
    assert_true("total_chunks" in data, f"unexpected stats payload: {data}")
    record(
        "Initial stats",
        True,
        f"total_chunks={data.get('total_chunks')} by_modality={data.get('by_modality')}",
    )
    return data


def step_corpus_inventory() -> dict[str, Any]:
    status, data = request("GET", "/corpus")
    assert_true(status == 200, f"expected 200, got {status}")
    assert_true("documents" in data, f"unexpected corpus payload: {data}")
    assert_true(data.get("total_chunks", 0) >= len(data.get("documents", [])), "chunk/document counts are inconsistent")
    if data.get("documents"):
        first = data["documents"][0]
        for key in ("document_id", "asset_url", "chunk_count", "chunks"):
            assert_true(key in first, f"missing corpus document key {key}: {first}")
    record(
        "Corpus inventory",
        True,
        f"documents={data.get('document_count')} chunks={data.get('total_chunks')}",
    )
    return data


def step_ingest_once() -> dict[str, Any]:
    status, data = request("POST", "/ingest", {"source": "filesystem", "path": SAMPLE_PATH})
    assert_true(status == 200, f"expected 200, got {status}: {data}")
    assert_true(data.get("failed") == 0, f"ingest failures: {data}")
    assert_true(data.get("ingested", 0) + data.get("skipped", 0) > 0, f"no files processed: {data}")
    record(
        "Ingest sample data",
        True,
        f"ingested={data.get('ingested')} skipped={data.get('skipped')} failed={data.get('failed')}",
    )
    return data


def step_ingest_idempotent(previous_total: int) -> dict[str, Any]:
    status, data = request("POST", "/ingest", {"source": "filesystem", "path": SAMPLE_PATH})
    assert_true(status == 200, f"expected 200, got {status}: {data}")
    assert_true(data.get("failed") == 0, f"second ingest failures: {data}")

    stats_status, stats = request("GET", "/stats")
    assert_true(stats_status == 200, f"expected stats 200, got {stats_status}")
    current_total = stats.get("total_chunks", -1)
    assert_true(
        current_total >= previous_total,
        f"chunk count decreased after idempotent ingest: before={previous_total} after={current_total}",
    )
    record(
        "Repeat ingest idempotency",
        True,
        f"second_ingested={data.get('ingested')} skipped={data.get('skipped')} total_chunks={current_total}",
    )
    return stats


def step_search(query: str, expected_hint: str | None = None) -> dict[str, Any]:
    status, data = request("POST", "/search", {"query_text": query, "n_results": 5})
    assert_true(status == 200, f"expected 200, got {status}: {data}")
    results_list = data.get("results", [])
    assert_true(results_list, f"no search results for query={query!r}")
    top = results_list[0]
    assert_true("score" in top and "snippet" in top and "asset_url" in top, f"bad result schema: {top}")
    hint_present = None
    if expected_hint:
        haystack = json.dumps(results_list[:3]).lower()
        hint_present = expected_hint.lower() in haystack
        if REQUIRE_SEMANTIC_MATCH:
            assert_true(hint_present, f"expected hint {expected_hint!r} not in top 3")
    hint_text = "" if hint_present is None else f" semantic_hint_present={hint_present}"
    record(
        f"Search '{query}'",
        True,
        f"total={data.get('total')} top_score={top.get('score')} top_asset={top.get('asset_url')}{hint_text}",
    )
    return data


def step_modality_filter() -> None:
    status, data = request(
        "POST",
        "/search",
        {"query_text": "diagram image", "n_results": 5, "modality_filter": ["image"]},
    )
    assert_true(status == 200, f"expected 200, got {status}: {data}")
    for item in data.get("results", []):
        assert_true(item.get("modality") == "image", f"non-image result returned: {item}")
    record("Image modality filter", True, f"image_results={len(data.get('results', []))}")


def step_eval() -> dict[str, Any]:
    started = time.monotonic()
    status, data = request("GET", "/eval")
    elapsed_ms = (time.monotonic() - started) * 1000
    assert_true(status == 200, f"expected 200, got {status}: {data}")
    for key in ("precision_at_1", "precision_at_5", "mrr", "total_queries"):
        assert_true(key in data, f"missing eval key {key}: {data}")
    assert_true(data.get("total_queries", 0) > 0, f"no eval queries: {data}")
    record(
        "Run eval",
        True,
        f"p@1={data.get('precision_at_1')} p@5={data.get('precision_at_5')} "
        f"mrr={data.get('mrr')} elapsed_ms={elapsed_ms:.1f}",
    )
    return data


def step_bad_ingest_error() -> None:
    status, data = request("POST", "/ingest", {"source": "filesystem", "path": "./missing/path"})
    assert_true(status == 404, f"expected 404 for missing path, got {status}: {data}")
    record("Bad ingest error handling", True, f"status={status} detail={data.get('detail')}")


def main() -> int:
    log("=" * 78)
    log("Dashboard/API integration workflow")
    log(f"BASE_URL={BASE_URL}")
    log(f"SAMPLE_PATH={SAMPLE_PATH}")
    log("=" * 78)

    workflow = [
        ("Dashboard loads", step_dashboard_loads),
        ("Health check", step_health),
        ("Initial stats", step_initial_stats),
        ("Ingest sample data", step_ingest_once),
    ]

    state: dict[str, Any] = {}
    try:
        for name, func in workflow:
            log(f"\n--- {name} ---")
            state[name] = func()

        before_total = int(step_initial_stats().get("total_chunks", 0))

        log("\n--- Repeat ingest idempotency ---")
        state["Repeat ingest idempotency"] = step_ingest_idempotent(before_total)

        log("\n--- Corpus inventory ---")
        step_corpus_inventory()

        log("\n--- Search onboarding ---")
        step_search("onboarding", expected_hint="onboarding")

        log("\n--- Search deployment workflow ---")
        step_search("kubernetes rollback", expected_hint="deployment")

        log("\n--- Image modality filter ---")
        step_modality_filter()

        log("\n--- Stats after ingest ---")
        stats = step_initial_stats()
        assert_true(stats.get("total_chunks", 0) > 0, "expected chunks after ingest")

        log("\n--- Run eval ---")
        step_eval()

        log("\n--- Bad ingest error handling ---")
        step_bad_ingest_error()

    except Exception as exc:
        record("Workflow stopped", False, str(exc))

    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    log("\n" + "=" * 78)
    log(f"SUMMARY: passed={passed} failed={failed}")
    for result in results:
        status = "PASS" if result.passed else "FAIL"
        log(f"- {status}: {result.name} | {result.details}")
    log("=" * 78)
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
