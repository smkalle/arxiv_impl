"""Streamlit admin console for the metaorch orchestrator.

Talks to the FastAPI service over HTTP (default http://127.0.0.1:8000).
Run from the orchestrator/ directory:

    streamlit run streamlit_app.py
"""

from __future__ import annotations

import json
from typing import Any

import requests
import streamlit as st

DEFAULT_BASE_URL = "http://127.0.0.1:8000"

# --------------------------------------------------------------------------- #
# session-state helpers
# --------------------------------------------------------------------------- #


def _state() -> dict[str, Any]:
    if "metaorch" not in st.session_state:
        st.session_state.metaorch = {
            "base_url": DEFAULT_BASE_URL,
            "last_run": None,        # full run JSON
            "last_run_id": None,
            "run_history": [],       # list[(run_id, status, started_at)]
            "nav_page": "Dashboard", # internal mirror of _metaorch_nav widget key
        }
    return st.session_state.metaorch


def _api(method: str, path: str, **kw: Any) -> requests.Response:
    s = _state()
    url = s["base_url"].rstrip("/") + path
    try:
        return requests.request(method, url, timeout=20, **kw)
    except requests.RequestException as e:
        # return a synthetic 599 so callers can render a friendly message
        class _Err(requests.Response):
            def __init__(self, exc: Exception) -> None:
                super().__init__()
                self.status_code = 599
                self._exc = exc

            def json(self, *a: Any, **k: Any) -> dict[str, Any]:
                return {"error": str(self._exc)}

            @property
            def text(self) -> str:
                return str(self._exc)

        return _Err(e)


# --------------------------------------------------------------------------- #
# pages
# --------------------------------------------------------------------------- #


def page_dashboard() -> None:
    st.header("Dashboard")
    r = _api("GET", "/health")
    if r.status_code != 200:
        st.error(f"health check failed ({r.status_code}): {r.text}")
        return
    h = r.json()
    c1, c2, c3 = st.columns(3)
    c1.metric("Status", h["status"])
    c2.metric("Adapters loaded", h["adapters_loaded"])
    c3.metric("Version", h["version"])
    st.subheader("Stages available")
    st.write(", ".join(h["stages_available"]))

    st.subheader("Pipeline DAG")
    pr = _api("GET", "/pipelines")
    if pr.status_code == 200:
        p = pr.json()
        st.caption(f"canonical plan: **{p['name']}**")
        st.code(" -> ".join(p["stages"]), language="text")
        dag = p["dag"]
        # render the adjacency list as a small table
        rows = [{"stage": k, "depends_on": ", ".join(v) or "(root)"} for k, v in dag.items()]
        st.table(rows)


def page_stages() -> None:
    st.header("Stage contracts")
    r = _api("GET", "/stages")
    if r.status_code != 200:
        st.error(f"failed to load stages ({r.status_code}): {r.text}")
        return
    stages = r.json()
    for s in stages:
        with st.expander(f"{s['kind']}  ·  {s['adapter_name']} v{s['adapter_version']}"):
            c1, c2 = st.columns(2)
            c1.markdown("**Input keys**")
            c1.code("\n".join(s["input_keys"]), language="text")
            c2.markdown("**Output keys**")
            c2.code("\n".join(s["output_keys"]), language="text")


def page_run() -> None:
    st.header("Trigger a run")

    st.subheader("Plan")
    col_a, col_b = st.columns(2)
    with col_a:
        stages_str = st.text_area(
            "stages (comma-separated, empty = canonical full run)",
            value="INGEST, KB_ENRICH, MM_SEARCH, CATALOG, RETRIEVE, TICKETMIND, EVOLVE, COEVOLVE",
            height=68,
        )
    with col_b:
        resume_from = st.selectbox(
            "resume_from",
            ["(none)", "INGEST", "KB_ENRICH", "MM_SEARCH", "CATALOG",
             "RETRIEVE", "TICKETMIND", "EVOLVE", "COEVOLVE"],
        )

    st.subheader("Context overrides")
    ticket_text = st.text_input(
        "ticket_text",
        value="how do I reset my MFA on the mobile app?",
    )
    acl_groups = st.text_input("acl_groups (comma-separated)", value="eng-all")
    sku_ids = st.text_input("sku_ids (comma-separated)", value="RAK-TEST-001, RAK-TEST-002")
    sources = st.text_input("sources (comma-separated)", value="gs1, open_food_facts")

    with st.expander("KB articles (JSON list) — empty uses defaults"):
        default_kb = (
            '[\n'
            '  {"article_id": "kb-mfa-reset", "title": "Resetting multi-factor authentication",\n'
            '   "body": "To reset MFA: open settings, tap Security, choose Reset MFA, verify via SMS...",\n'
            '   "product_area": "identity", "last_updated": "2026-04-01T00:00:00Z"},\n'
            '  {"article_id": "kb-mobile-auth", "title": "Mobile authenticator enrollment",\n'
            '   "body": "Enroll a new mobile authenticator device under Security > Devices > Add.",\n'
            '   "product_area": "identity", "last_updated": "2026-03-15T00:00:00Z"},\n'
            '  {"article_id": "kb-sms-codes", "title": "SMS verification codes",\n'
            '   "body": "SMS verification codes expire after 5 minutes.",\n'
            '   "product_area": "notifications", "last_updated": "2026-02-20T00:00:00Z"}\n'
            ']'
        )
        kb_text = st.text_area("kb_articles", value=default_kb, height=180)

    with st.expander("Per-stage configs (JSON) — optional"):
        cfg_text = st.text_area(
            "stage_configs",
            value='{"RETRIEVE": {"top_k": 5}, "COEVOLVE": {"mode": "rqgm", "budget": 80}}',
            height=120,
        )

    if st.button("Run pipeline", type="primary"):
        # ---- assemble payload ----
        plan: dict[str, Any] = {}
        parsed_stages = [s.strip() for s in stages_str.split(",") if s.strip()]
        if parsed_stages:
            plan["stages"] = parsed_stages
        if resume_from != "(none)":
            plan["resume_from"] = resume_from
        try:
            plan["stage_configs"] = json.loads(cfg_text) if cfg_text.strip() else {}
        except json.JSONDecodeError as e:
            st.error(f"stage_configs is not valid JSON: {e}")
            return

        context: dict[str, Any] = {}
        if ticket_text.strip():
            context["ticket_text"] = ticket_text.strip()
        if acl_groups.strip():
            context["acl_groups"] = [a.strip() for a in acl_groups.split(",") if a.strip()]
        if sku_ids.strip():
            context["sku_ids"] = [s.strip() for s in sku_ids.split(",") if s.strip()]
        if sources.strip():
            context["sources"] = [s.strip() for s in sources.split(",") if s.strip()]
        try:
            kb = json.loads(kb_text) if kb_text.strip() else None
        except json.JSONDecodeError as e:
            st.error(f"kb_articles is not valid JSON: {e}")
            return
        if kb:
            context["kb_articles"] = kb

        payload = {"plan": plan, "context": context}

        with st.spinner("Executing pipeline…"):
            r = _api("POST", "/runs", json=payload)
        if r.status_code != 200:
            st.error(f"run failed ({r.status_code}): {r.text}")
            return
        run = r.json()["run"]
        s = _state()
        s["last_run"] = run
        s["last_run_id"] = run["run_id"]
        s["run_history"].insert(
            0, (run["run_id"], run["status"], run.get("started_at"))
        )
        s["run_history"] = s["run_history"][:25]
        st.success(f"Run {run['run_id']} → **{run['status']}**")
        s["nav_page"] = "Results"
        st.rerun()


def page_results() -> None:
    st.header("Results")
    s = _state()
    run = s["last_run"]

    # allow fetching a prior run by id
    with st.form("fetch_run"):
        rid = st.text_input("run_id to fetch", value=s["last_run_id"] or "")
        fetched = st.form_submit_button("Load run")
    if fetched and rid.strip():
        r = _api("GET", f"/runs/{rid.strip()}")
        if r.status_code == 200:
            run = r.json()["run"]
            s["last_run"] = run
            s["last_run_id"] = run["run_id"]
        else:
            st.error(f"not found ({r.status_code}): {r.text}")
            run = None

    if run is None:
        st.info("No run loaded. Trigger one from the Run page.")
        return

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Status", run["status"])
    c2.metric("Stages", len(run["stage_results"]))
    c3.metric("Started", (run.get("started_at") or "")[11:19])
    c4.metric("Finished", (run.get("finished_at") or "")[11:19])
    st.caption(f"run_id: `{run['run_id']}`")

    st.subheader("Stage results")
    for sr in run["stage_results"]:
        stage = sr["stage"]
        prov = sr["provenance"]
        status = prov["status"]
        icon = {"ok": "✅", "skipped": "⏭️", "failed": "❗"}.get(status, "•")
        title = f"{icon} {stage} · {prov['adapter']} v{prov['adapter_version']} · {prov['duration_ms']} ms"
        with st.expander(title, expanded=(status != "ok")):
            if prov.get("error"):
                st.error(f"error: {prov['error']}")

            cc1, cc2 = st.columns(2)
            with cc1:
                st.markdown("**Inputs summary**")
                st.json(prov["inputs_summary"] or {})
            with cc2:
                st.markdown("**Outputs summary**")
                st.json(prov["outputs_summary"] or {})

            st.markdown("**Artifacts**")
            st.json(sr.get("artifacts") or {})


def page_history() -> None:
    st.header("Run history (this session)")
    s = _state()
    hist = s["run_history"]
    if not hist:
        st.info("No runs in this session yet.")
        return
    st.table(
        [{"run_id": rid[:13] + "…", "status": st_, "started": (ts or "")[11:19]}
         for rid, st_, ts in hist]
    )
    if st.button("Clear history"):
        s["run_history"] = []
        st.rerun()


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

PAGES = {
    "Dashboard": page_dashboard,
    "Stages": page_stages,
    "Run": page_run,
    "Results": page_results,
    "History": page_history,
}


def main() -> None:
    st.set_page_config(
        page_title="metaorch admin",
        page_icon="🧩",
        layout="wide",
    )
    s = _state()

    with st.sidebar:
        st.markdown("## 🧩 metaorch admin")
        base = st.text_input("API base URL", value=s["base_url"], key="base_url_input")
        if base != s["base_url"]:
            s["base_url"] = base
        # live health indicator
        h = _api("GET", "/health")
        if h.status_code == 200:
            st.success("API reachable", icon="✅")
        else:
            st.error("API unreachable", icon="⚠️")
        st.caption(f"(health: {h.status_code})")

        st.divider()
        # Sync internal nav state -> widget key BEFORE the widget renders so
        # programmatic navigation (s["nav_page"] = "Results"; st.rerun()) is
        # honoured. Setting a widget key before instantiation is allowed; setting
        # it after is not (the original crash).
        if st.session_state.get("_metaorch_nav") != s["nav_page"]:
            st.session_state["_metaorch_nav"] = s["nav_page"]
        current = st.radio("Page", list(PAGES.keys()), key="_metaorch_nav")
        s["nav_page"] = current
        st.divider()
        st.caption("In-memory run store — history resets with the API process.")

    PAGES[current]()


if __name__ == "__main__":
    main()