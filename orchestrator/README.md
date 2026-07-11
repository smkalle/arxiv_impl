# orchestrator — Meta-Orchestrator Pipeline (metaorch)

A standalone arxiv_impl subproject that **chains all eight sibling subprojects' use cases into one end-to-end pipeline** via minimal contract-bound adapters:

```
INGEST (AAFLOW) → KB_ENRICH (SIRA KB Ingestor) ─┐
                                                 ├──> RETRIEVE (SIRA)     ──┐
MM_SEARCH (Jina ek_search)             ────── ──┤                          │
                                                 └──> TICKETMIND (TKMEM) ──┤
CATALOG (DataMaster)                   ──────── (parallel root)            ├──> EVOLVE (EvolveMem) → COEVOLVE (RGQM)
                                                                            │
                                                                            ─┘
```

The orchestrator does **not** import any sibling subproject's code. Each adapter reimplements a thin fake that honours the contract shape documented in the corresponding sibling's spec — input keys, output keys, and a small set of headline invariants (see `SPEC.md` §5). The executor validates contracts at stage boundaries, executes the DAG in dependency order, and records per-stage provenance (counts/hashes only — never raw payloads).

## Stack

- Python 3.10+, FastAPI, Pydantic v2, pytest. `cd orchestrator && python3 -m pytest` is the only test command.
- In-memory runtime — no FAISS, LanceDB, Ollama, Jina API, Chroma. All adapter outputs are deterministic fakes.
- Optional Streamlit admin console (`pip install -e ".[ui]"`).

## Install

```bash
cd orchestrator
pip install -e "."              # core: fastapi, pydantic, uvicorn
pip install -e ".[dev]"         # + pytest, httpx for tests
pip install -e ".[ui]"          # + streamlit, requests for admin console
```

## Local quickstart

```bash
cd orchestrator
python3 -m pytest                       # full test suite
python3 -m uvicorn metaorch.api.main:app --port 8000

curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -s http://127.0.0.1:8000/pipelines | python3 -m json.tool
curl -s http://127.0.0.1:8000/stages | python3 -m json.tool
curl -s -X POST http://127.0.0.1:8000/runs \
  -H 'content-type: application/json' -d '{}' | python3 -m json.tool | head
```

A bare `POST /runs {}` defaults to the canonical full run with `default_context()` (a built-in ticket + KB + SKU fixture), so the entire 8-stage DAG runs out of the box.

## Streamlit admin console

A browser-based admin UI that wraps the FastAPI API. The API service must be running first.

```bash
cd orchestrator
pip install -e ".[ui]"                                       # streamlit + requests
python3 -m uvicorn metaorch.api.main:app --port 8000         # terminal 1: API
streamlit run streamlit_app.py --server.port 8501            # terminal 2: UI
```

Open `http://127.0.0.1:8501`. The console provides:

| Page | Description |
|---|---|
| **Dashboard** | Health summary, adapter count, version, canonical DAG adjacency table. |
| **Stages** | All 8 stage contracts (adapter name, version, input/output keys) in expandable sections. |
| **Run** | Editable form to trigger `POST /runs`: stage list, `resume_from`, context overrides (`ticket_text`, `acl_groups`, `sku_ids`, `sources`, `kb_articles` JSON), per-stage `stage_configs` JSON. A successful run auto-navigates to the Results page. |
| **Results** | Per-stage provenance (inputs/outputs summaries as counts/hashes), expandable artifacts JSON, and a form to load any prior run by `run_id`. |
| **History** | In-session run list (up to 25 runs; cleared when the API process restarts). |

The sidebar shows a live health indicator and an editable API base URL (default `http://127.0.0.1:8000`).

## What's NOT here (by design)

- Real ML backends. Adapters produce fakes honouring each subproject's documented contract.
- Persistence. `RunStore` is in-memory; runs vanish when the process exits.
- Cross-subproject imports. Tests must pass with **no sibling subproject on PYTHONPATH**.

## Docs

- `AGENTS.md` — contributor guide, table of stage contracts, module layout.
- `SPEC.md` — canonical spec; if `AGENTS.md` conflicts, trust `SPEC.md`.
