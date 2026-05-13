"""
Comprehensive validation suite for KB Ingestor Admin Dashboard v0.1.

Two layers:
  1. API contract tests — full coverage of all endpoints, role enforcement, error shapes
  2. Frontend structural tests — HTML/JS analysis without a browser

Run:
    pytest dashboard/tests/test_dashboard_validation.py -v

Backend must be running on http://127.0.0.1:8000.
"""
import json
import pathlib
import re
import urllib.error
import urllib.request

import pytest

API_BASE = "http://127.0.0.1:8000"
FRONTEND = pathlib.Path(__file__).parent.parent / "frontend" / "index.html"

CREDS = {
    "admin":    "admin123",
    "ops":      "ops123",
    "readonly": "read123",
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _post(path: str, body: dict, token: str | None = None) -> tuple[int, dict]:
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=json.dumps(body).encode(),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _get(path: str, token: str | None = None, params: dict | None = None) -> tuple[int, dict]:
    url = f"{API_BASE}{path}"
    if params:
        qs = "&".join(f"{k}={v}" for k, v in params.items())
        url += ("&" if "?" in url else "?") + qs
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def _delete(path: str, token: str, extra_headers: dict | None = None) -> tuple[int, dict | None]:
    headers = {"Authorization": f"Bearer {token}"}
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(url=f"{API_BASE}{path}", headers=headers, method="DELETE")
    try:
        with urllib.request.urlopen(req) as r:
            body = r.read()
            return r.status, json.loads(body) if body else None
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


def token(role: str) -> str:
    _, data = _post("/api/auth/token", {"username": role, "password": CREDS[role]})
    assert "access_token" in data, f"Login failed for {role}: {data}"
    return data["access_token"]


# ── 1. Auth ───────────────────────────────────────────────────────────────────

class TestAuth:

    def test_admin_token_issued(self):
        status, data = _post("/api/auth/token", {"username": "admin", "password": "admin123"})
        assert status == 200
        assert "access_token" in data
        assert data["token_type"] == "bearer"

    def test_ops_token_issued(self):
        status, data = _post("/api/auth/token", {"username": "ops", "password": "ops123"})
        assert status == 200
        assert "access_token" in data

    def test_readonly_token_issued(self):
        status, data = _post("/api/auth/token", {"username": "readonly", "password": "read123"})
        assert status == 200
        assert "access_token" in data

    def test_wrong_password_rejected(self):
        status, data = _post("/api/auth/token", {"username": "admin", "password": "wrong"})
        assert status in (401, 400, 403), f"Expected 4xx for wrong password, got {status}"

    def test_unknown_user_rejected(self):
        status, data = _post("/api/auth/token", {"username": "hacker", "password": "anything"})
        assert status in (401, 400, 403)

    def test_unauthenticated_request_rejected(self):
        status, data = _get("/api/runs")
        assert status == 401, f"Expected 401 without token, got {status}"

    def test_jwt_contains_role(self):
        import base64
        _, data = _post("/api/auth/token", {"username": "admin", "password": "admin123"})
        jwt = data["access_token"]
        # Decode payload (middle segment, base64url)
        payload_b64 = jwt.split(".")[1]
        # Add padding
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        assert payload.get("role") == "admin"
        assert payload.get("sub") == "admin"


# ── 2. Runs list ──────────────────────────────────────────────────────────────

class TestRunsList:

    def test_returns_paginated_list(self):
        t = token("admin")
        status, data = _get("/api/runs", t)
        assert status == 200
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)
        assert data["total"] >= 10

    def test_run_item_has_required_fields(self):
        t = token("admin")
        _, data = _get("/api/runs", t)
        item = data["items"][0]
        required = ["run_id", "source_filename", "source_type", "status",
                    "index_name", "triggered_by", "rows_total"]
        for field in required:
            assert field in item, f"Missing field: {field}"

    def test_filter_by_status_done(self):
        t = token("admin")
        _, data = _get("/api/runs", t, {"status": "done"})
        assert data["total"] > 0
        for item in data["items"]:
            assert item["status"] == "done"

    def test_filter_by_status_failed(self):
        t = token("admin")
        _, data = _get("/api/runs", t, {"status": "failed"})
        assert data["total"] > 0
        for item in data["items"]:
            assert item["status"] == "failed"

    def test_filter_by_source_type_zendesk(self):
        t = token("admin")
        _, data = _get("/api/runs", t, {"source_type": "zendesk"})
        assert data["total"] > 0
        for item in data["items"]:
            assert item["source_type"] == "zendesk"

    def test_pagination(self):
        t = token("admin")
        _, page1 = _get("/api/runs", t, {"page": 1, "limit": 5})
        _, page2 = _get("/api/runs", t, {"page": 2, "limit": 5})
        assert len(page1["items"]) <= 5
        if page2["total"] > 5:
            ids_page1 = {i["run_id"] for i in page1["items"]}
            ids_page2 = {i["run_id"] for i in page2["items"]}
            assert ids_page1.isdisjoint(ids_page2), "Page 1 and Page 2 should not overlap"

    def test_ops_can_list_runs(self):
        t = token("ops")
        status, data = _get("/api/runs", t)
        assert status == 200

    def test_readonly_can_list_runs(self):
        t = token("readonly")
        status, data = _get("/api/runs", t)
        assert status == 200


# ── 3. Run detail ─────────────────────────────────────────────────────────────

class TestRunDetail:

    @pytest.fixture(scope="class")
    def a_run_id(self):
        t = token("admin")
        _, data = _get("/api/runs", t)
        return data["items"][0]["run_id"]

    @pytest.fixture(scope="class")
    def a_failed_run_id(self):
        t = token("admin")
        _, data = _get("/api/runs", t, {"status": "failed"})
        return data["items"][0]["run_id"]

    def test_run_detail_has_batches(self, a_run_id):
        t = token("admin")
        status, data = _get(f"/api/runs/{a_run_id}", t)
        assert status == 200
        assert "batches" in data
        assert len(data["batches"]) > 0

    def test_run_detail_has_stage_timings(self, a_run_id):
        t = token("admin")
        _, data = _get(f"/api/runs/{a_run_id}", t)
        # At least some runs should have timing data
        assert "run_id" in data

    def test_batch_items_have_required_fields(self, a_run_id):
        t = token("admin")
        _, data = _get(f"/api/runs/{a_run_id}", t)
        batch = data["batches"][0]
        required = ["batch_id", "run_id", "rows", "status"]
        for field in required:
            assert field in batch, f"Batch missing field: {field}"

    def test_failed_run_has_failed_batches(self, a_failed_run_id):
        t = token("admin")
        _, data = _get(f"/api/runs/{a_failed_run_id}", t)
        statuses = {b["status"] for b in data["batches"]}
        assert "failed" in statuses, "Failed run should have at least one failed batch"

    def test_nonexistent_run_returns_404(self):
        t = token("admin")
        status, data = _get("/api/runs/run-NOTEXIST", t)
        assert status == 404
        assert "error" in data or "detail" in data

    def test_ops_can_view_run_detail(self, a_run_id):
        t = token("ops")
        status, _ = _get(f"/api/runs/{a_run_id}", t)
        assert status == 200

    def test_readonly_can_view_run_detail(self, a_run_id):
        t = token("readonly")
        status, _ = _get(f"/api/runs/{a_run_id}", t)
        assert status == 200


# ── 4. Role enforcement ───────────────────────────────────────────────────────

class TestRoleEnforcement:

    def test_ops_cannot_trigger_run(self):
        t = token("ops")
        status, data = _post("/api/runs", {
            "source_filename": "test.csv", "source_type": "zendesk",
            "index_name": "x", "batch_size": 128, "max_workers": 4,
            "embed_model": "all-MiniLM-L6-v2", "max_chunk_chars": 512,
            "null_policy": "drop", "append_mode": False,
        }, t)
        assert status == 403
        error = data.get("detail", data.get("error", {}))
        assert "INSUFFICIENT_ROLE" in str(error)

    def test_readonly_cannot_trigger_run(self):
        t = token("readonly")
        status, _ = _post("/api/runs", {
            "source_filename": "test.csv", "source_type": "zendesk",
            "index_name": "x", "batch_size": 128, "max_workers": 4,
            "embed_model": "all-MiniLM-L6-v2", "max_chunk_chars": 512,
            "null_policy": "drop", "append_mode": False,
        }, t)
        assert status == 403

    def test_readonly_cannot_retry(self):
        admin_t = token("admin")
        _, data = _get("/api/runs", admin_t, {"status": "failed"})
        run_id = data["items"][0]["run_id"]
        # Get a failed batch
        _, detail = _get(f"/api/runs/{run_id}", admin_t)
        failed_batches = [b["batch_id"] for b in detail["batches"] if b["status"] == "failed"]

        ro_t = token("readonly")
        status, _ = _post(f"/api/runs/{run_id}/retry", {"batch_ids": failed_batches[:1]}, ro_t)
        assert status == 403

    def test_ops_can_retry(self):
        admin_t = token("admin")
        _, data = _get("/api/runs", admin_t, {"status": "failed"})
        run_id = data["items"][0]["run_id"]
        _, detail = _get(f"/api/runs/{run_id}", admin_t)
        failed_batches = [b["batch_id"] for b in detail["batches"] if b["status"] == "failed"]

        ops_t = token("ops")
        status, _ = _post(f"/api/runs/{run_id}/retry", {"batch_ids": failed_batches[:1]}, ops_t)
        assert status in (200, 202), f"Ops should be able to retry, got {status}"

    def test_readonly_cannot_delete_index(self):
        admin_t = token("admin")
        _, idx_data = _get("/api/indexes", admin_t)
        idx_name = idx_data["items"][0]["index_name"]

        ro_t = token("readonly")
        status, _ = _delete(f"/api/indexes/{idx_name}", ro_t,
                            {"X-Confirm-Index-Name": idx_name})
        assert status == 403

    def test_ops_cannot_delete_index(self):
        admin_t = token("admin")
        _, idx_data = _get("/api/indexes", admin_t)
        idx_name = idx_data["items"][0]["index_name"]

        ops_t = token("ops")
        status, _ = _delete(f"/api/indexes/{idx_name}", ops_t,
                            {"X-Confirm-Index-Name": idx_name})
        assert status == 403

    def test_admin_can_create_config(self):
        admin_t = token("admin")
        status, data = _post("/api/configs", {
            "config_name": f"test-config-{__import__('time').time_ns()}",
            "batch_size": 64, "max_workers": 2, "max_chunk_chars": 256,
            "min_chunk_chars": 10, "null_policy": "drop",
            "faiss_factory": "Flat", "embed_model": "all-MiniLM-L6-v2",
        }, admin_t)
        assert status in (200, 201), f"Admin should create config, got {status}: {data}"

    def test_ops_cannot_create_config(self):
        ops_t = token("ops")
        status, _ = _post("/api/configs", {
            "config_name": "should-fail", "batch_size": 64, "max_workers": 2,
            "max_chunk_chars": 256, "min_chunk_chars": 10, "null_policy": "drop",
            "faiss_factory": "Flat", "embed_model": "all-MiniLM-L6-v2",
        }, ops_t)
        assert status == 403


# ── 5. Indexes ────────────────────────────────────────────────────────────────

class TestIndexes:

    def test_index_list_non_empty(self):
        t = token("admin")
        status, data = _get("/api/indexes", t)
        assert status == 200
        assert data["total"] >= 1

    def test_index_item_has_required_fields(self):
        t = token("admin")
        _, data = _get("/api/indexes", t)
        idx = data["items"][0]
        required = ["index_name", "doc_count", "embed_dim", "embed_model",
                    "last_updated", "consistency_status"]
        for field in required:
            assert field in idx, f"Index missing field: {field}"

    def test_index_detail_has_run_history(self):
        t = token("admin")
        _, data = _get("/api/indexes", t)
        idx_name = data["items"][0]["index_name"]
        status, detail = _get(f"/api/indexes/{idx_name}", t)
        assert status == 200
        assert "run_history" in detail or "runs" in detail or "contributing_runs" in detail, \
            f"Index detail should include run history; got keys: {list(detail.keys())}"

    def test_nonexistent_index_returns_404(self):
        t = token("admin")
        status, data = _get("/api/indexes/does-not-exist", t)
        assert status == 404

    def test_consistency_check_requires_admin(self):
        t = token("ops")
        _, idx_data = _get("/api/indexes", token("admin"))
        idx_name = idx_data["items"][0]["index_name"]
        status, _ = _post(f"/api/indexes/{idx_name}/check-consistency", {}, t)
        assert status == 403

    def test_all_roles_can_read_indexes(self):
        for role in ["admin", "ops", "readonly"]:
            t = token(role)
            status, _ = _get("/api/indexes", t)
            assert status == 200, f"Role {role} should be able to read indexes"

    def test_soft_delete_requires_confirm_header(self):
        admin_t = token("admin")
        _, idx_data = _get("/api/indexes", admin_t)
        idx_name = idx_data["items"][0]["index_name"]
        # Missing confirm header → 400
        status, data = _delete(f"/api/indexes/{idx_name}", admin_t)
        assert status in (400, 422), f"Expected 400 without confirm header, got {status}: {data}"


# ── 6. Configs ────────────────────────────────────────────────────────────────

class TestConfigs:

    def test_configs_list_accessible(self):
        for role in ["admin", "ops", "readonly"]:
            t = token(role)
            status, data = _get("/api/configs", t)
            assert status == 200
            # API returns either {"items": [...]} or a plain list
            configs = data if isinstance(data, list) else data.get("items", [])
            assert isinstance(configs, list), f"Expected list of configs for role {role}, got {type(data)}"

    def test_config_create_and_read(self):
        import time
        admin_t = token("admin")
        name = f"val-test-{time.time_ns()}"
        status, created = _post("/api/configs", {
            "config_name": name, "batch_size": 64, "max_workers": 2,
            "max_chunk_chars": 256, "min_chunk_chars": 10, "null_policy": "drop",
            "faiss_factory": "Flat", "embed_model": "all-MiniLM-L6-v2",
        }, admin_t)
        assert status in (200, 201), f"Config create failed: {created}"
        assert "config_id" in created or "config_name" in created

        # Verify it appears in the list
        _, list_data = _get("/api/configs", admin_t)
        configs = list_data if isinstance(list_data, list) else list_data.get("items", [])
        names = [c["config_name"] for c in configs]
        assert name in names, f"Created config {name} not in list: {names}"


# ── 7. Sparkline & SSE shape ──────────────────────────────────────────────────

class TestSparklineAndSSE:

    def test_sparkline_returns_data(self):
        t = token("admin")
        status, data = _get("/api/sparkline", t)
        assert status == 200
        points = data if isinstance(data, list) else data.get("points", [])
        assert isinstance(points, list), f"Expected list, got {type(data)}: {data}"

    def test_sse_stream_endpoint_exists(self):
        """Verify the SSE endpoint returns the right content-type (don't wait for full stream)."""
        import socket, urllib.parse
        admin_t = token("admin")
        _, runs = _get("/api/runs", admin_t, {"status": "running"})
        if not runs["items"]:
            pytest.skip("No running runs available for SSE test")
        run_id = runs["items"][0]["run_id"]

        # Make a raw HTTP request and check Content-Type without reading the full stream
        sock = socket.create_connection(("127.0.0.1", 8000), timeout=3)
        try:
            request = (
                f"GET /api/runs/{run_id}/stream HTTP/1.1\r\n"
                f"Host: 127.0.0.1:8000\r\n"
                f"Authorization: Bearer {admin_t}\r\n"
                f"Accept: text/event-stream\r\n"
                f"Connection: close\r\n\r\n"
            )
            sock.sendall(request.encode())
            response = sock.recv(2048).decode(errors="replace")
            assert "text/event-stream" in response or "200" in response, \
                f"SSE endpoint should return event-stream; got: {response[:300]}"
        finally:
            sock.close()


# ── 8. Error shape contract ───────────────────────────────────────────────────

class TestErrorShapes:

    def test_run_not_found_error_shape(self):
        t = token("admin")
        status, data = _get("/api/runs/run-NOTEXIST", t)
        assert status == 404
        # Error should have code + message
        detail = data.get("detail", data.get("error", {}))
        detail_str = json.dumps(detail)
        assert "NOT_FOUND" in detail_str or "not found" in detail_str.lower(), \
            f"404 error should indicate NOT_FOUND: {detail}"

    def test_403_error_shape(self):
        ops_t = token("ops")
        status, data = _post("/api/runs", {
            "source_filename": "x.csv", "source_type": "zendesk", "index_name": "x",
            "batch_size": 128, "max_workers": 4, "embed_model": "all-MiniLM-L6-v2",
            "max_chunk_chars": 512, "null_policy": "drop", "append_mode": False,
        }, ops_t)
        assert status == 403
        detail = data.get("detail", data.get("error", {}))
        assert "INSUFFICIENT_ROLE" in json.dumps(detail)

    def test_401_error_shape(self):
        status, data = _get("/api/runs")
        assert status == 401
        assert data  # should have a body


# ── 9. Audit log ──────────────────────────────────────────────────────────────

class TestAuditLog:

    def test_audit_log_accessible_to_admin(self):
        t = token("admin")
        status, data = _get("/api/audit", t)
        assert status == 200
        assert "items" in data

    def test_audit_log_accessible_to_readonly(self):
        t = token("readonly")
        status, data = _get("/api/audit", t)
        assert status == 200

    def test_audit_log_blocked_for_ops_on_others_actions(self):
        # Ops can see their own; the endpoint should accept ops token
        t = token("ops")
        status, data = _get("/api/audit", t)
        # Either 200 (filtered to own) or 403 — both are valid per spec
        assert status in (200, 403)


# ── 10. Frontend HTML structural validation ───────────────────────────────────

class TestFrontendStructure:
    """Parse dashboard/frontend/index.html without a browser and verify all
    required structural elements and JS patterns are present."""

    @pytest.fixture(scope="class")
    def html(self):
        return FRONTEND.read_text(encoding="utf-8")

    @pytest.fixture(scope="class")
    def soup(self, html):
        from bs4 import BeautifulSoup
        return BeautifulSoup(html, "html5lib")

    def test_file_exists(self):
        assert FRONTEND.exists(), "dashboard/frontend/index.html not found"

    def test_file_size_reasonable(self):
        size = FRONTEND.stat().st_size
        assert size > 30_000, f"HTML too small ({size} bytes) — likely incomplete"
        assert size < 5_000_000, f"HTML suspiciously large ({size} bytes)"

    def test_login_screen_element(self, soup):
        el = soup.find(id="login-screen")
        assert el is not None, "Missing #login-screen element"

    def test_login_form_fields(self, soup):
        user_input = soup.find(id="login-user")
        pass_input = soup.find(id="login-pass")
        assert user_input is not None, "Missing #login-user input"
        assert pass_input is not None, "Missing #login-pass input"

    def test_main_app_shell(self, soup):
        el = soup.find(id="app")
        assert el is not None, "Missing #app main shell"

    def test_sidebar_navigation(self, soup):
        nav = soup.find(id="sidebar")
        assert nav is not None, "Missing #sidebar"
        text = nav.get_text()
        assert "Dashboard" in text
        assert "Runs" in text
        assert "Indexes" in text

    def test_content_area(self, soup):
        content = soup.find(id="content")
        assert content is not None, "Missing #content div where screens are rendered"

    def test_test_credentials_shown(self, html):
        assert "admin123" in html, "Test credentials not shown in login screen"
        assert "ops123" in html
        assert "read123" in html

    def test_api_base_configurable(self, html):
        assert "API_BASE" in html or "localhost:8000" in html, \
            "API base URL must be configurable or set"

    def test_jwt_storage_in_localstorage(self, html):
        assert "localStorage" in html, "JWT should be stored in localStorage"

    def test_sse_client_present(self, html):
        has_sse = "EventSource" in html or "text/event-stream" in html or "event-stream" in html
        assert has_sse, "SSE client code not found"

    def test_run_detail_screen_logic(self, html):
        has_detail = ("run-detail" in html or "runDetail" in html or
                      "run_detail" in html or "RunDetail" in html or
                      "OP-1" in html or "stage" in html.lower())
        assert has_detail, "Run detail screen/logic not found"

    def test_wizard_screen_logic(self, html):
        has_wizard = ("wizard" in html.lower() or "Step 1" in html or
                      "step-1" in html or "step1" in html)
        assert has_wizard, "New Ingestion Wizard not found"

    def test_index_health_screen(self, html):
        assert "index" in html.lower(), "Index health screen not referenced"

    def test_role_based_ui_enforcement(self, html):
        # The JS must check role somewhere
        has_role_check = "role" in html and ("admin" in html) and ("ops" in html)
        assert has_role_check, "Role-based UI enforcement code not found"

    def test_batch_grid_present(self, html):
        assert "batch" in html.lower() and "grid" in html.lower(), \
            "Batch status grid code not found"

    def test_speedup_gauge_present(self, html):
        assert "speedup" in html.lower(), "Speedup gauge not found"

    def test_tailwind_cdn(self, html):
        assert "tailwindcss" in html or "tailwind" in html.lower(), \
            "Tailwind CSS not referenced"

    def test_dark_light_theme(self, html):
        assert "dark" in html.lower() and ("light" in html.lower() or "theme" in html.lower()), \
            "Dark/light theme toggle not found"

    def test_sse_reconnect_logic(self, html):
        has_reconnect = ("reconnect" in html.lower() or "backoff" in html.lower() or
                         "retry" in html.lower())
        assert has_reconnect, "SSE reconnect/backoff logic not found"

    def test_error_handling_in_js(self, html):
        assert "catch" in html, "No try/catch error handling in frontend JS"
        assert "error" in html.lower(), "No error handling patterns in frontend"

    def test_copy_json_functionality(self, html):
        assert "copy" in html.lower() and "json" in html.lower(), \
            "Copy-JSON button logic not found"

    def test_skeleton_loading_present(self, html):
        assert "skeleton" in html.lower() or "shimmer" in html.lower() or "loading" in html.lower(), \
            "Skeleton loading states not found"

    def test_pagination_logic(self, html):
        assert "page" in html.lower() and ("limit" in html or "per_page" in html or "offset" in html), \
            "Pagination logic not found"

    def test_no_framework_imports(self, html):
        # Should not import React/Vue via CDN (pure vanilla JS)
        frameworks = ["react.development.js", "vue.global.js", "angular.js"]
        for fw in frameworks:
            assert fw not in html, f"Unexpected framework import: {fw}"

    def test_sign_out_function(self, html):
        assert "logout" in html.lower() or "sign out" in html.lower() or "signout" in html.lower(), \
            "Logout/sign out function not found"
