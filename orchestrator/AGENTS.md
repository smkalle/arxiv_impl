# orchestrator — Meta-Orchestrator Pipeline (metaorch)

A standalone subproject that **chains all eight arxiv_impl subprojects' use cases into one end-to-end pipeline**: ticket ingest → KB enrichment → (parallel retrieval legs: SIRA / TicketMind / multimodal knowledge search) → catalog enrichment → self-improvement (EvolveMem AutoResearch → RGQM agent co-evolution).

Implements **minimal adapters** against the documented contracts of each subproject — it does **not** import any sibling subproject's code. Each adapter is an in-memory fake honouring the contract's input/output shape, validated at stage boundaries. The orchestrator's job is to (1) declare the DAG, (2) validate contracts, (3) execute stages in dependency order, (4) capture provenance per stage, (5) expose the result via FastAPI.

## Stack and hard constraints

- Python 3.10+, FastAPI, Pydantic v2, pytest. `cd orchestrator && python3 -m pytest` is the only test command.
- **Adapters do not import sibling subprojects.** Each adapter reimplements the documented contract from that subproject's spec. Coupling is by contract, not by code.
- **In-memory runtime only.** No LanceDB/FAISS/Ollama/Jina. Outputs are fakes that fulfil the contract shape. Real backends belong in the sibling subprojects — this project's job is orchestration and contract validation, not reimplementation of ML pipelines.
- **Provenance is a first-class output.** Every `StageResult` carries a `Provenance` block: adapter name+version, started_at/finished_at, duration_ms, stage config, input+output summaries (counts/hashes, never payloads), status (ok/skipped/failed), optional error.
- **Contract violations abort the run.** `adapter.validate_inputs` / `validate_outputs` raise `ContractError`; the executor marks the stage `failed`, the run `failed`, and halts (no partial downstream side-effects).
- **Resume from stage.** `RunPlan.resume_from` skips every stage topologically preceding the named stage by marking it `skipped`; the upstream outputs must be re-supplied in `PipelineContext` (or supplied as fake fixtures).
- **No persistent store.** A `RunStore` keeps in-memory runs keyed by `run_id`. No file/database. A run is gone when the process exits.
- **Optional Streamlit admin console** (`streamlit_app.py`) wraps the HTTP API; install with `pip install -e ".[ui]"`. It is a thin client — no business logic, no direct adapter access.

---

## Pipeline DAG

```
                ┌──> INGEST     ──┐
                │                ├──> RETRIEVE   ──┐
                ├──> KB_ENRICH  ──┤                │
                │                └──> TICKETMIND ──┤
                │                                   ├──> EVOLVE  ──> COEVOLVE
                └──> MM_SEARCH   ───────────────── ──┘

CATALOG   (independent tributary leg, parallel; outputs feed EVOLVE as evidence)
```

Adjacency (deps):
- `INGEST`:    []
- `KB_ENRICH`: []
- `MM_SEARCH`: []   (multimodal knowledge-search leg)
- `CATALOG`:   []   (commerce catalog enrichment leg)
- `RETRIEVE`:  [`INGEST`, `KB_ENRICH`]
- `TICKETMIND`:[`INGEST`, `KB_ENRICH`]
- `EVOLVE`:    [`RETRIEVE`, `TICKETMIND`, `MM_SEARCH`]
- `COEVOLVE`:  [`EVOLVE`]

The canonical "full run" plan is: `[INGEST, KB_ENRICH, MM_SEARCH, CATALOG, RETRIEVE, TICKETMIND, EVOLVE, COEVOLVE]` (topological). The executor runs roots in declaration order, fans-in at `RETRIEVE`/`TICKETMIND`, fans-in at `EVOLVE`, and finishes with `COEVOLVE`.

---

## Stage contracts (8 adapters)

Each adapter file lives in `metaorch/adapters/`. Each adapter declares: `kind`, `name`, `version`, `validate_inputs(dict)`, `validate_outputs(dict)`, `run(inputs, config) -> dict`. The output shape mirrors that subproject's documented public contract.

| Stage | Kind | Mirrors subproject | Input shape (keys) | Output shape (keys) |
|---|---|---|---|---|
| 1 | `INGEST` | AAFLOW (`kb-ingestor`) | `source_path`, `source_type` ("zendesk"|"jira"), `batch_size`, `embed_model` | `arrow_path`, `faiss_path`, `run_summary{ rows_ingested, batches, throughput_rps, embed_dim }`, `table_schema{ columns: [..] }` |
| 2 | `KB_ENRICH` | SIRA KB Ingestor (+ SIRA enrich contract) | `kb_articles[{ article_id, title, body, product_area, last_updated }]`, `ollama_model`, `tau`, `weight_w` | `enriched_kb_path`, `kb_index_path`, `setup_summary{ kb_articles, enriched_terms_total, elapsed_s, retrieval_defaults{ tau, weight_w, top_k } }`, `enriched_corpus[{ article_id, enriched_body, enriched_terms[] }]` |
| 3 | `MM_SEARCH` | Jina `ek_search` | `query_text`, `n_results`, `modality_filter[]`, `source_filter[]`, `acl_groups[]` | `results[{ id, score, modality, source_system, snippet }]`, `total`, `query_latency_ms`, `backend_used` ("stub"), `embed_dim` |
| 4 | `RETRIEVE` | SIRA | `ticket_text`, `top_k`, `tau`, `weight_w`, `corpus[{ article_id, title, enriched_body, enriched_terms[] }]` | `results[{ article_id, title, score, matched_original_terms, matched_enriched_terms, snippet }]`, `sketch_terms_generated`, `sketch_terms_validated`, `sketch_terms_rejected`, `fallback_used`, `fallback_reason?`, `latency_ms` |
| 5 | `TICKETMIND` | TKMEM TicketMind | `ticket_text`, `top_k`, `filters{ product_area?, date_from? }`, `session_id?` | `results[{ kb_id, title, score, matched_terms, view_contributions{ semantic, lexical, symbolic }, snippet }]`, `retrieval_trace{ query_plan, latency_ms, evolved_config_version }` |
| 6 | `CATALOG` | DataMaster CatalogAgent | `sku_ids[]`, `sources[]`, `min_delta_threshold`, `dry_run` | `job_id`, `status` ("queued"|"running"|"completed"|"failed"), `skus_processed`, `skus_enriched`, `skus_rejected`, `avg_score_delta`, `manifests_committed`, `provenance_artifact` |
| 7 | `EVOLVE` | EvolveMem AutoResearch | `start_from` ("L1"|"L2"|"L3"|"L4"), `only`?, `baseline_f1`, `max_rounds` | `loop_results[{ loop_id, rounds_run, baseline_fitness, best_fitness, accepted_patches[], discovered_dimensions[] }]`, `final_config_version` ("baseline"|"evolved"), `fitness_gain` |
| 8 | `COEVOLVE` | RGQM EpochForge Lite | `mode` ("rqgm"|"hgm_h"), `budget`, `checkpoint`, `task_set` | `final_archive_summary{ nodes, utility_records, epoch_events }`, `coder_pass_rate`, `blended_tokens`, `baseline_tokens` (hgm_h), `erasure_invariant_holds: bool`, `epoch_events[{ step, action, promoted? }]` |

Invariants each adapter's `validate_outputs` enforces (the headline contract from each subproject's spec):

- **INGEST**: `run_summary.embed_dim` is present and an int; `table_schema` is non-empty.
- **KB_ENRICH**: `setup_summary.retrieval_defaults.{tau,weight_w,top_k}` all present; `enriched_corpus` length equals input corpus length.
- **MM_SEARCH**: `embed_dim` > 0; every result `score` in [0,1]; `backend_used` is one of {stub,local,jina_api}.
- **RETRIEVE**: if `fallback_used` is true, `fallback_reason` is present; `latency_ms` is an int ≥ 0; `sketch_terms_rejected` is a subset of `sketch_terms_generated`.
- **TICKETMIND**: for every result, `view_contributions.{semantic,lexical,symbolic}` are present floats ≥ 0; `retrieval_trace.evolved_config_version` ∈ {"baseline","evolved"}.
- **CATALOG**: if `dry_run` was true, `manifests_committed == 0`; if `status == "completed"`, `avg_score_delta` is `None` or a float.
- **EVOLVE**: `final_config_version` ∈ {"baseline","evolved"}; if `final_config_version == "evolved"`, at least one `accepted_patches` entry exists in `loop_results`; `fitness_gain >= 0`.
- **COEVOLVE**: if `mode == "rqgm"`, `erasure_invariant_holds == true` and exactly one `epoch_events` entry has `action` containing "epoch" (simplified); `blended_tokens <= baseline_tokens` when `mode == "rqgm"` (the headline P0).

---

## Run plan and provenance

`POST /runs` takes:

```json
{
  "stages": ["INGEST","KB_ENRICH","MM_SEARCH","CATALOG","RETRIEVE","TICKETMIND","EVOLVE","COEVOLVE"],
  "stage_configs": { "RETRIEVE": { "top_k": 5 }, "COEVOLVE": { "mode": "rqgm", "budget": 80 } },
  "resume_from": null,
  "context": { "ticket_text": "how do I reset my MFA?", "kb_articles": [...] }
}
```

Response: `PipelineRun` with per-stage `StageResult{ stage, provenance, artifacts }`. The `provenance` block records `inputs_summary` and `outputs_summary` as **counts/hashes only**, never raw payloads.

---

## Module layout

```
orchestrator/
  AGENTS.md            (this file)
  SPEC.md              (canonical contract — out-of-band with this AGENTS.md; if it conflicts, trust SPEC)
  README.md            (table-of-contents entry for the root README)
  pyproject.toml       (deps + console script `metaorch`; optional [ui] extras for streamlit)
  pytest.ini
  streamlit_app.py     (optional Streamlit admin console — thin HTTP client over the API)
  metaorch/
    __init__.py
    models.py          (Pydantic v2: StageKind, Provenance, StageResult, RunPlan, PipelineRun, PipelineContext)
    config.py          (Settings: env METAORCH_* defaults; adapter registry)
    contract.py        (Adapter Protocol + DAG definition + helpers)
    errors.py          (ContractError, AdapterError, StageFailed, MissingAdapter)
    executor.py        (PipelineExecutor: topo-sort, validate, run, prove)
    pipeline.py        (canonical "full run" RunPlan builder + default context)
    adapters/
      __init__.py      (registers all 8 adapters)
      base.py
      aaflow_adapter.py        (INGEST)
      sira_ingestor_adapter.py (KB_ENRICH)
      jina_adapter.py          (MM_SEARCH)
      sira_adapter.py          (RETRIEVE)
      tkmem_adapter.py         (TICKETMIND)
      datamaster_adapter.py    (CATALOG)
      evolvemem_adapter.py     (EVOLVE)
      rgqm_adapter.py         (COEVOLVE)
    api/
      __init__.py
      main.py            (FastAPI app + small `cli()` for `metaorch`)
      routes.py          (GET /pipelines, GET /stages, POST /runs, GET /runs/{id}, GET /health)
      deps.py            (RunStore + executor singletons)
      schemas.py         (HTTP request/response models)
  tests/
    __init__.py
    conftest.py
    test_contract.py    (validate_inputs/validate_outputs for every adapter — the contract surface)
    test_adapters.py    (each adapter's `run` produces the documented output shape)
    test_executor.py    (DAG topological order, resume_from, contract failure halts, provenance recorded)
    test_api.py         (TestClient against routes; /pipelines, /stages, /runs happy + error paths)
```

---

## Run it

```bash
cd orchestrator
python3 -m pytest                 # all tests
python3 -m metaorch               # start uvicorn on 127.0.0.1:8000 (console entry)
# or:
python3 -m uvicorn metaorch.api.main:app --port 8000

curl -s http://127.0.0.1:8000/pipelines | jq .
curl -s -X POST http://127.0.0.1:8000/runs \
  -H 'content-type: application/json' \
  -d @examples/full_run.json | jq .status
```

### Streamlit admin console (optional)

```bash
cd orchestrator
pip install -e ".[ui]"            # streamlit + requests
python3 -m uvicorn metaorch.api.main:app --port 8000   # terminal 1: API
streamlit run streamlit_app.py --server.port 8501      # terminal 2: UI
```

The console is a thin HTTP client over the FastAPI API — no direct adapter access, no business logic. See `README.md` for the page-by-page breakdown.

## What is NOT in scope (explicitly)

- Real ML backends (FAISS, LanceDB, Ollama, Jina API, CatalogLab). Adapters produce fakes.
- Cross-subproject imports. The orchestrator must be installable/testable without any sibling subproject on `PYTHONPATH`.
- Persistent run storage. `RunStore` is in-memory.
- Business logic in the Streamlit console. `streamlit_app.py` is a thin HTTP client only — all logic stays in the executor and adapters.
- Evolving/chaining of multiple full runs. One full run per request.