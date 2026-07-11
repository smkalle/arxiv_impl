"""Live end-to-end smoke test against a freshly-booted uvicorn service.

Starts uvicorn as a subprocess, exercises the HTTP surface with httpx, tears it down.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parent
PORT = 8055
BASE = f"http://127.0.0.1:{PORT}"


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _wait_for_health(client: httpx.Client, timeout: float = 8.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = client.get("/health", timeout=0.5)
            if r.status_code == 200:
                return True
        except httpx.HTTPError:
            pass
        time.sleep(0.15)
    return False


def main() -> int:
    port = _free_port()
    base = f"http://127.0.0.1:{port}"
    results: list[tuple[str, str, str]] = []  # (name, expected, actual)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "metaorch.api.main:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(ROOT),
        env={**os.environ, "PYTHONPATH": str(ROOT)},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        with httpx.Client(base_url=base, timeout=10.0) as c:
            if not _wait_for_health(c):
                results.append(("service-boot", "200", "DOWN"))
                print("\n".join(f"{n}: expect {e} got {a}" for n, e, a in results))
                return 1

            # 1. health
            r = c.get("/health")
            body = r.json()
            results.append(("health", "200", str(r.status_code)))
            assert_eq("health.adapters_loaded=8", "8", str(body["adapters_loaded"]), results)
            assert_eq("health.stages=8", "8", str(len(body["stages_available"])), results)

            # 2. pipelines
            r = c.get("/pipelines")
            p = r.json()
            results.append(("pipelines", "200", str(r.status_code)))
            assert_eq("pipelines.stages=8", "8", str(len(p["stages"])), results)
            assert_eq("pipelines.dag.RETRIEVE",
                      "['INGEST', 'KB_ENRICH']", sorted(p["dag"]["RETRIEVE"]), results)

            # 3. list stages
            r = c.get("/stages")
            stages = r.json()
            results.append(("list-stages", "200", str(r.status_code)))
            assert_eq("list-stages.count", "8", str(len(stages)), results)

            # 4. happy full run
            r = c.post("/runs", json={})
            run = r.json()["run"]
            results.append(("full-run", "completed", run["status"]))
            assert_eq("full-run.stages", "8", str(len(run["stage_results"])), results)
            statuses = [s["provenance"]["status"] for s in run["stage_results"]]
            assert_eq("full-run.all-ok", "8", str(statuses.count("ok")), results)
            run_id = run["run_id"]

            # 5. get run by id
            r = c.get(f"/runs/{run_id}")
            results.append(("get-run-by-id", "200", str(r.status_code)))

            # 6. unknown run -> 404
            r = c.get("/runs/does-not-exist")
            results.append(("unknown-run", "404", str(r.status_code)))

            # 7. invalid plan missing deps -> 422
            r = c.post("/runs", json={"plan": {"stages": ["RETRIEVE"]}})
            results.append(("invalid-plan", "422", str(r.status_code)))

            # 8. resume_from COEVOLVE skips upstream
            r = c.post("/runs", json={"plan": {
                "stages": ["INGEST", "KB_ENRICH", "MM_SEARCH", "CATALOG",
                           "RETRIEVE", "TICKETMIND", "EVOLVE", "COEVOLVE"],
                "resume_from": "COEVOLVE"}})
            run = r.json()["run"]
            by = {s["stage"]: s["provenance"]["status"] for s in run["stage_results"]}
            # COEVOLVE executes; its hard transitive deps skip; CATALOG executes.
            results.append(("resume-COEVOLVE", "completed", run["status"]))
            assert_eq("resume-COEVOLVE.exec-coevolve", "ok", by["COEVOLVE"], results)
            assert_eq("resume-COEVOLVE.skip-evolve", "skipped", by["EVOLVE"], results)
            assert_eq("resume-COEVOLVE.skip-retrieve", "skipped", by["RETRIEVE"], results)
            assert_eq("resume-COEVOLVE.exec-catalog", "ok", by["CATALOG"], results)

            # 9. dry_run catalog
            r = c.post("/runs", json={
                "plan": {"stages": ["CATALOG"],
                         "stage_configs": {"CATALOG": {"dry_run": True}}},
                "context": {"sku_ids": ["A", "B"], "sources": ["gs1"]}})
            cat = r.json()["run"]["stage_results"][0]
            results.append(("dry-run", "completed", r.json()["run"]["status"]))
            assert_eq("dry-run.manifests", "0", str(cat["artifacts"]["manifests_committed"]), results)
            assert_eq("dry-run.avg-delta", "None", str(cat["artifacts"]["avg_score_delta"]), results)

            # 10. malformed json -> 422
            r = c.post("/runs", content=b"not json", headers={"content-type": "application/json"})
            results.append(("malformed-json", "422", str(r.status_code)))

            # 11. unknown stage -> 422
            r = c.post("/runs", json={"plan": {"stages": ["BOGUS"]}})
            results.append(("unknown-stage", "422", str(r.status_code)))

            # 12. concurrency - 10 parallel full runs
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
                futures = [pool.submit(c.post, "/runs", json={}) for _ in range(10)]
                codes = sorted({f.result().status_code for f in futures})
            assert_eq("concurrency-10.parallel-statuses", "[200]", str(codes), results)
            results.append(("concurrency-10", "[200]", str(codes)))

            # 13. huge ticket text
            big = "reset MFA " * 2000
            r = c.post("/runs", json={"context": {"ticket_text": big}})
            results.append(("huge-ticket", "completed", r.json()["run"]["status"]))

            # 14. health again (idempotent)
            r = c.get("/health")
            results.append(("health-again", "200", str(r.status_code)))

            # 15. POSTing the same data twice yields different run_ids (no dedup)
            r1 = c.post("/runs", json={})
            r2 = c.post("/runs", json={})
            ids = {r1.json()["run"]["run_id"], r2.json()["run"]["run_id"]}
            results.append(("idempotency-distinct-ids", "2", str(len(ids))))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()

    passed = sum(1 for _, e, a in results if e == a)
    failed = len(results) - passed
    print(f"\n=== Live HTTP smoke: {passed}/{len(results)} passed ({failed} failed) ===")
    for name, expected, actual in results:
        mark = "OK " if expected == actual else "FAIL"
        print(f"  [{mark}] {name}: expect {expected!r} got {actual!r}")
    return 1 if failed else 0


def assert_eq(name: str, expected: str, actual: object,
              results: list[tuple[str, str, str]]) -> None:
    a = str(actual)
    results.append((name, expected, a))


if __name__ == "__main__":
    sys.exit(main())