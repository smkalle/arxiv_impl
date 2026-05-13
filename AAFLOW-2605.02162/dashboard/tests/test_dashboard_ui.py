"""
Headless UI validation for KB Ingestor Admin Dashboard v0.1.
Runs against:
  - Backend:  http://127.0.0.1:8000  (must be running)
  - Frontend: file:// path to dashboard/frontend/index.html

Run:
    pytest dashboard/tests/test_dashboard_ui.py -v
"""
import json
import os
import pathlib
import time

import pytest
from playwright.sync_api import Page, expect, sync_playwright

# ── Config ────────────────────────────────────────────────────────────────────

FRONTEND = pathlib.Path(__file__).parent.parent / "frontend" / "index.html"
FRONTEND_URL = FRONTEND.as_uri()
API_BASE = "http://127.0.0.1:8000"

ADMIN_USER = "admin"
ADMIN_PASS = "admin123"
OPS_USER = "ops"
OPS_PASS = "ops123"
READONLY_USER = "readonly"
READONLY_PASS = "read123"


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope="session")
def browser_context():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            # Override API_BASE in the page so file:// → localhost:8000 works
            extra_http_headers={"Accept": "application/json"},
        )
        yield ctx
        browser.close()


@pytest.fixture
def page(browser_context):
    pg = browser_context.new_page()
    # Inject API_BASE override before any script runs
    pg.add_init_script(f"window.API_BASE = '{API_BASE}';")
    # Clear localStorage so each test starts from a logged-out state
    pg.goto(FRONTEND_URL)
    pg.evaluate("window.localStorage.clear()")
    pg.goto(FRONTEND_URL)
    yield pg
    pg.evaluate("window.localStorage.clear()")
    pg.close()


def login(page: Page, username: str, password: str):
    """Fill login form (page fixture already navigated and cleared localStorage)."""
    page.wait_for_selector("#login-screen", state="visible", timeout=8000)
    page.fill("#login-user", username)
    page.fill("#login-pass", password)
    # Click the Sign In button (no id — use text)
    page.click("button:has-text('Sign In')")
    # Wait until login screen is hidden (successful login)
    page.wait_for_selector("#login-screen", state="hidden", timeout=8000)


# ── API sanity checks (no browser needed) ────────────────────────────────────

class TestAPIEndpoints:
    """Fast API-level checks before running browser tests."""

    def _token(self, username, password):
        import urllib.request, json
        data = json.dumps({"username": username, "password": password}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/auth/token",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())["access_token"]

    def _get(self, path, token):
        import urllib.request, json
        req = urllib.request.Request(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req) as r:
            return json.loads(r.read())

    def test_auth_admin(self):
        token = self._token(ADMIN_USER, ADMIN_PASS)
        assert len(token) > 20

    def test_auth_ops(self):
        token = self._token(OPS_USER, OPS_PASS)
        assert len(token) > 20

    def test_auth_readonly(self):
        token = self._token(READONLY_USER, READONLY_PASS)
        assert len(token) > 20

    def test_runs_list_non_empty(self):
        token = self._token(ADMIN_USER, ADMIN_PASS)
        data = self._get("/api/runs", token)
        assert data["total"] >= 10, f"Expected ≥10 runs, got {data['total']}"

    def test_runs_status_filter(self):
        token = self._token(ADMIN_USER, ADMIN_PASS)
        done = self._get("/api/runs?status=done", token)
        failed = self._get("/api/runs?status=failed", token)
        assert done["total"] > 0, "No done runs found"
        assert failed["total"] > 0, "No failed runs found"
        for item in done["items"]:
            assert item["status"] == "done"
        for item in failed["items"]:
            assert item["status"] == "failed"

    def test_run_detail(self):
        token = self._token(ADMIN_USER, ADMIN_PASS)
        runs = self._get("/api/runs", token)
        run_id = runs["items"][0]["run_id"]
        detail = self._get(f"/api/runs/{run_id}", token)
        assert "batches" in detail
        assert len(detail["batches"]) > 0

    def test_indexes_list(self):
        token = self._token(ADMIN_USER, ADMIN_PASS)
        data = self._get("/api/indexes", token)
        assert data["total"] >= 1
        idx = data["items"][0]
        assert "index_name" in idx
        assert "doc_count" in idx
        assert "embed_dim" in idx
        assert "consistency_status" in idx

    def test_role_enforcement_ops_cannot_trigger_run(self):
        import urllib.request, json, urllib.error
        token = self._token(OPS_USER, OPS_PASS)
        data = json.dumps({
            "source_filename": "test.csv",
            "source_type": "zendesk",
            "index_name": "x",
            "batch_size": 128,
            "max_workers": 4,
            "embed_model": "all-MiniLM-L6-v2",
            "max_chunk_chars": 512,
            "null_policy": "drop",
            "append_mode": False,
        }).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/runs",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
        try:
            urllib.request.urlopen(req)
            pytest.fail("Expected 403 but got success")
        except urllib.error.HTTPError as e:
            assert e.code == 403

    def test_role_enforcement_readonly_cannot_retry(self):
        import urllib.request, json, urllib.error
        admin_token = self._token(ADMIN_USER, ADMIN_PASS)
        runs = self._get("/api/runs?status=failed", admin_token)
        run_id = runs["items"][0]["run_id"]

        ro_token = self._token(READONLY_USER, READONLY_PASS)
        data = json.dumps({"batch_ids": ["batch-00"]}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/runs/{run_id}/retry",
            data=data,
            method="POST",
            headers={
                "Authorization": f"Bearer {ro_token}",
                "Content-Type": "application/json",
            },
        )
        try:
            urllib.request.urlopen(req)
            pytest.fail("Expected 403 but got success")
        except urllib.error.HTTPError as e:
            assert e.code == 403

    def test_sparkline_endpoint(self):
        token = self._token(ADMIN_USER, ADMIN_PASS)
        data = self._get("/api/sparkline", token)
        # Returns either a list or {"points": [...]}
        points = data if isinstance(data, list) else data.get("points", data)
        assert isinstance(points, list), f"Expected list of sparkline points, got: {data}"


# ── Browser UI tests ──────────────────────────────────────────────────────────

class TestLoginScreen:

    def test_login_screen_shown_on_load(self, page):
        page.goto(FRONTEND_URL)
        expect(page.locator("#login-screen")).to_be_visible(timeout=8000)

    def test_login_screen_shows_test_credentials(self, page):
        page.goto(FRONTEND_URL)
        page.wait_for_selector("#login-screen", state="visible", timeout=8000)
        content = page.locator("#login-screen").inner_text()
        assert "admin" in content.lower(), "Login screen should mention admin credentials"

    def test_wrong_password_shows_error(self, page):
        page.goto(FRONTEND_URL)
        page.wait_for_selector("#login-screen", state="visible", timeout=8000)
        page.fill("#login-user", "admin")
        page.fill("#login-pass", "wrongpassword")
        page.click("button:has-text('Sign In')")
        # Login screen should remain visible after bad credentials
        page.wait_for_timeout(2500)
        expect(page.locator("#login-screen")).to_be_visible()

    def test_admin_login_succeeds(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        # Main app shell (#app) should now be visible
        expect(page.locator("#app")).to_be_visible(timeout=5000)

    def test_ops_login_succeeds(self, page):
        login(page, OPS_USER, OPS_PASS)
        expect(page.locator("#app")).to_be_visible(timeout=5000)


class TestDashboardHome:

    def test_kpi_strip_visible(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        # Wait for KPI values to load (they come from API)
        page.wait_for_timeout(2000)
        # KPI strip should show non-zero values
        kpi_text = page.locator("body").inner_text()
        # Should contain ticket counts, run status, index size
        assert any(word in kpi_text for word in ["Active", "Indexed", "Index", "Speedup", "Run"]), \
            "KPI strip labels not found"

    def test_runs_table_populated(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        page.wait_for_timeout(2000)
        # Should have run rows (look for run-XXXX pattern)
        content = page.locator("body").inner_text()
        assert "run-" in content, "No run IDs found in page"

    def test_status_badges_present(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        page.wait_for_timeout(2000)
        content = page.locator("body").inner_text()
        has_status = any(s in content for s in ["Done", "Failed", "Running", "Partial", "done", "failed", "running"])
        assert has_status, "No status badges found in runs table"

    def test_nav_sidebar_visible(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        # Sidebar navigation should be present
        sidebar = page.locator("nav, aside, [id*='sidebar'], [id*='nav']").first
        expect(sidebar).to_be_visible(timeout=3000)

    def test_ops_user_sees_dashboard(self, page):
        login(page, OPS_USER, OPS_PASS)
        page.wait_for_timeout(2000)
        content = page.locator("body").inner_text()
        assert "run-" in content, "Ops user should see run history"


class TestRunDetail:

    def _get_a_failed_run_id(self):
        import urllib.request, json
        data = json.dumps({"username": ADMIN_USER, "password": ADMIN_PASS}).encode()
        req = urllib.request.Request(
            f"{API_BASE}/api/auth/token",
            data=data,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req) as r:
            token = json.loads(r.read())["access_token"]

        req2 = urllib.request.Request(
            f"{API_BASE}/api/runs?status=failed&limit=1",
            headers={"Authorization": f"Bearer {token}"},
        )
        with urllib.request.urlopen(req2) as r:
            data = json.loads(r.read())
        return data["items"][0]["run_id"]

    def test_run_detail_navigates_from_table(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        page.wait_for_timeout(2000)
        # Click a "View" or "Detail" link, or click a run ID
        # Look for clickable run ID links or view buttons
        run_links = page.locator("a[href*='run'], [data-run-id], button:has-text('View'), a:has-text('run-')")
        if run_links.count() > 0:
            run_links.first.click()
            page.wait_for_timeout(2000)
            content = page.locator("body").inner_text()
            # Should show stage timeline or batch information
            has_detail = any(kw in content for kw in ["OP-1", "OP-2", "batch", "Batch", "Stage", "Load", "Embed"])
            assert has_detail, "Run detail page did not load expected content"
        else:
            pytest.skip("No run detail links found — may need hash navigation")

    def test_run_detail_via_hash(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        # Navigate directly using hash routing
        run_id = self._get_a_failed_run_id()
        page.evaluate(f"window.location.hash = '#/runs/{run_id}'")
        page.wait_for_timeout(3000)
        content = page.locator("body").inner_text()
        # Should show run ID on page
        assert run_id in content or "batch" in content.lower() or "stage" in content.lower(), \
            f"Run detail for {run_id} did not render expected content; got: {content[:300]}"

    def test_failed_run_shows_error_info(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        run_id = self._get_a_failed_run_id()
        page.evaluate(f"window.location.hash = '#/runs/{run_id}'")
        page.wait_for_timeout(3000)
        content = page.locator("body").inner_text()
        has_error_info = any(kw in content for kw in [
            "Failed", "failed", "Error", "error", "batch", "Batch"
        ])
        assert has_error_info, f"Failed run detail should show error info; got: {content[:300]}"


class TestIndexHealth:

    def test_index_health_screen(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        page.evaluate("window.location.hash = '#/indexes'")
        page.wait_for_timeout(3000)
        content = page.locator("body").inner_text()
        has_index = any(kw in content for kw in [
            "support-kb", "billing-kb", "Doc Count", "doc_count", "Embedding", "embed", "Index"
        ])
        assert has_index, f"Index health screen should list indexes; got: {content[:400]}"

    def test_index_consistency_status(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        page.evaluate("window.location.hash = '#/indexes'")
        page.wait_for_timeout(3000)
        content = page.locator("body").inner_text()
        # Should show consistency check result
        has_consistency = any(kw in content for kw in [
            "ok", "OK", "consistent", "Consistent", "✓", "mismatch", "unchecked"
        ])
        assert has_consistency, "Index health screen should show consistency status"


class TestRoleBasedUI:

    def test_admin_sees_new_ingestion_nav(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        content = page.locator("body").inner_text()
        assert any(kw in content for kw in ["New Ingestion", "Trigger", "new ingestion"]), \
            "Admin should see New Ingestion navigation item"

    def test_ops_cannot_access_wizard_screen(self, page):
        login(page, OPS_USER, OPS_PASS)
        page.evaluate("window.location.hash = '#/runs/new'")
        page.wait_for_timeout(2000)
        content = page.locator("body").inner_text()
        # Should either redirect away or show access denied
        wizard_shown = any(kw in content for kw in ["Step 1", "Source Upload", "Batch Size"])
        if wizard_shown:
            # If the wizard is shown to ops, the Start button should be disabled
            start_btn = page.locator("button:has-text('Start Ingestion')")
            if start_btn.count() > 0:
                # Should be disabled for ops
                assert start_btn.first.is_disabled() or "disabled" in (start_btn.first.get_attribute("class") or ""), \
                    "Start Ingestion should be disabled for Ops role"

    def test_role_badge_in_sidebar(self, page):
        login(page, OPS_USER, OPS_PASS)
        content = page.locator("body").inner_text()
        # The role should be visible somewhere in the UI
        assert any(r in content.lower() for r in ["ops", "admin", "readonly"]), \
            "User role should be displayed in the UI"


class TestWizard:

    def test_wizard_renders_for_admin(self, page):
        login(page, ADMIN_USER, ADMIN_PASS)
        page.evaluate("window.location.hash = '#/runs/new'")
        page.wait_for_timeout(2000)
        content = page.locator("body").inner_text()
        has_wizard = any(kw in content for kw in [
            "Step 1", "Source", "Upload", "Batch", "Model", "wizard", "Wizard"
        ])
        assert has_wizard, f"Wizard should render for admin; got: {content[:400]}"
