# metaorch — Specification

Canonical spec for the `orchestrator/` subproject: a meta-orchestrator pipeline that chains all eight `arxiv_impl` subprojects' use cases end-to-end via minimal contract-bound adapters. If anything in `AGENTS.md` conflicts with this file, **trust this file**.

## 1. Purpose

The eight sibling subprojects under `arxiv_impl/` each implement one arXiv paper's technique for a single use case: ticket ingest (AAFLOW), KB enrichment (SIRA KB Ingestor), ticket retrieval (SIRA), multimodal knowledge search (Jina `ek_search`), TicketMind 3-view hybrid (TKMEM), e-commerce catalog enrichment (DataMaster), retrieval self-improvement (EvolveMem AutoResearch), and agent co-evolution (RGQM EpochForge Lite). Each ships with its own docs/scripts/deps and is consumed by others in ad-hoc ways (e.g. AAFLOW feeds SIRA, SIRA feeds EvolveMem).

`metaorch` is the **single place** that defines how they compose as one pipeline. It is intentionally **decoupled**: adapters reimplement thin fakes against each subproject's documented public contract (see `AGENTS.md` for the contract table), validating data shape at stage boundaries and recording provenance. The orchestrator's job is orchestration + contract validation, not ML.

## 2. Non-goals

- Not a replacement for any sibling subproject (no ML / no real indexes).
- Not persistent across process restarts.
- Not a UI. HTTP API only.
- Not a test harness for the sibling subprojects (each tests itself).

## 3. The pipeline DAG

```
                ┌──> INGEST     ──┐
                │                ├──> RETRIEVE   ──┐
                ├──> KB_ENRICH  ──┤                │
                │                └──> TICKETMIND ──┤
                │                                   ├──> EVOLVE  ──> COEVOLVE
                └──> MM_SEARCH   ───────────────── ──┘

CATALOG   (independent tributary leg, parallel; outputs feed EVOLVE as evidence)
```

Strict adjacency:

| Stage | Depends on |
|---|---|
| `INGEST` | — |
| `KB_ENRICH` | — |
| `MM_SEARCH` | — |
| `CATALOG` | — |
| `RETRIEVE` | `INGEST`, `KB_ENRICH` |
| `TICKETMIND` | `INGEST`, `KB_ENRICH` |
| `EVOLVE` | `RETRIEVE`, `TICKETMIND`, `MM_SEARCH` |
| `COEVOLVE` | `EVOLVE` |

Topological order is non-unique; the canonical full-run plan uses:
`[INGEST, KB_ENRICH, MM_SEARCH, CATALOG, RETRIEVE, TICKETMIND, EVOLVE, COEVOLVE]`.

The executor should treat `CATALOG` as evidence that `EVOLVE` ingests (via `PipelineContext` fan-in) but `CATALOG` is **not** a strict contract dependency of `EVOLVE` — `EVOLVE` runs even if `CATALOG` is absent or `skipped`.

## 4. Adapter contract

Every adapter implements the `Adapter` Protocol from `metaorch/contract.py`:

```python
class Adapter(Protocol):
    kind: StageKind
    name: str
    version: str
    def validate_inputs(self, inputs: dict) -> None: ...
    def validate_outputs(self, outputs: dict) -> None: ...
    def run(self, inputs: dict, config: dict) -> dict: ...
```

- `validate_inputs` raises `ContractError` if a required key is missing or has the wrong type.
- `validate_outputs` raises `ContractError` if the output is missing required keys or violates a stage's headline invariant (see §5).
- `run` is deterministic, in-memory, side-effect-free, and **does not** call any sibling subproject's code.

## 5. Per-stage input/output contracts (authoritative)

The full key table lives in `AGENTS.md` § "Stage contracts"; the **headline invariants** that validators enforce are normative here:

- `INGEST` (AAFLOW) — `run_summary.embed_dim` is int; `table_schema` non-empty.
- `KB_ENRICH` (SIRA KB Ingestor + SIRA) — `setup_summary.retrieval_defaults` is fully populated; `enriched_corpus` length matches input.
- `MM_SEARCH` (Jina `ek_search`) — every result `score ∈ [0,1]`; `backend_used ∈ {stub,local,jina_api}`; `embed_dim > 0`.
- `RETRIEVE` (SIRA) — `fallback_used ⇒ fallback_reason` present; `latency_ms: int ≥ 0`; `sketch_terms_rejected ⊆ sketch_terms_generated`.
- `TICKETMIND` (TKMEM) — every result `view_contributions.{semantic,lexical,symbolic}` are floats ≥ 0; `retrieval_trace.evolved_config_version ∈ {baseline, evolved}`.
- `CATALOG` (DataMaster) — `dry_run ⇒ manifests_committed == 0`; `status==completed ⇒ avg_score_delta ∈ float|None`.
- `EVOLVE` (EvolveMem) — `final_config_version ∈ {baseline, evolved}`; if evolved then ≥ one `accepted_patches`; `fitness_gain ≥ 0`.
- `COEVOLVE` (RGQM) — if `mode==rqgm`: `erasure_invariant_holds == true`, exactly one epoch boundary event present; `blended_tokens ≤ baseline_tokens`.

## 6. Provenance

A `Provenance` block is recorded **per stage**:

```
Provenance{
  stage: StageKind,
  adapter: str,           # adapter.name
  adapter_version: str,
  started_at: datetime,
  finished_at: datetime,
  duration_ms: int,
  config: dict,           # the StageConfig that was applied
  inputs_summary: dict,   # counts/hashes only — NEVER raw payloads
  outputs_summary: dict,  # counts/hashes only
  status: "ok"|"skipped"|"failed",
  error: str | None
}
```

Payloads stay in `StageResult.artifacts`; provenance summaries are squashed to integers/hashes so logs are safe to print and store.

## 7. Executor semantics

1. Validate every requested `stage` has a registered adapter. Raise `MissingAdapter` otherwise.
2. Topologically order respecting the DAG in §3. Reject a plan if it would violate the DAG (e.g. missing a hard dependency). `CATALOG` is optional w.r.t. `EVOLVE`.
3. For each stage in order:
   - If `resume_from` is set and this stage topologically preceeds it: mark `skipped`, do not call the adapter.
   - Otherwise gather inputs from `PipelineContext` + upstream `StageResult.artifacts` per the contract table in `AGENTS.md`.
   - `adapter.validate_inputs` — on failure: stage `failed`, run `failed`, halt.
   - `t0 = now(); out = adapter.run(inputs, config); t1 = now()`.
   - `adapter.validate_outputs` — on failure: same as above.
   - Build `StageResult{ stage, provenance, artifacts }` with status `ok`.
4. Return `PipelineRun{ run_id, plan, started_at, finished_at, status, stage_results[] }`.

A `ContractError` from either validator or a raised exception from `adapter.run` halts the entire run; downstream stages are NOT marked `skipped`, they simply do not execute. The run status is `failed`. (This is intentional: silent skipping on a contract failure would mask bugs.)

## 8. HTTP API

- `GET  /health` → `{ status, adapters_loaded, stages_available, version }`
- `GET  /pipelines` → `{ name, stages, dag: { stage: [deps...] } }`
- `GET  /stages` → list of `{ kind, adapter_name, adapter_version, input_keys, output_keys }`
- `POST /runs` body = `RunRequest{ plan: RunPlan, context: PipelineContext }` → `PipelineRun`
- `GET  /runs/{run_id}` → stored `PipelineRun` or 404.

`RunStore` is an in-process dict keyed by `run_id` (a UUID4 string). No persistence.

## 9. Env config

Settings are read from `METAORCH_*` env vars (see `metaorch/config.py::Settings`). Defaults keep everything in-memory and side-effect-free. No secrets are required.

## 10. Tests

Four test files mirror the four layers:

- `test_contract.py` — every adapter's `validate_inputs`/`validate_outputs` positive + negative.
- `test_adapters.py` — `run()` returns the documented output shape for a representative input.
- `test_executor.py` — topo order, resume_from skips upstream, contract failure halts, provenance recorded for every stage, full run completes happy path.
- `test_api.py` — TestClient against `routes.py`; covers `/health`, `/pipelines`, `/stages`, `POST /runs` (happy + dry_run on CATALOG + resume_from COEVOLVE), and 404 on missing run.

All tests must pass with `python3 -m pytest` from inside the `orchestrator/` folder, with **no sibling subproject on `PYTHONPATH`**.

## 11. Open issues

- `O-1`: `CATALOG`'s relationship to `EVOLVE` — currently a "soft" evidence feed via context fan-in, not a hard contract dependency. Re-evaluate once the EvolveMem contract for evidence ingestion is concrete.
- `O-2`: A streaming variant of `POST /runs` (SSE per stage completion) is desirable but not in v0.1.
- `O-3`: Adapter versioning — adapters declare `version: str` but there is no matrix of which adapter versions compose with which. v0.1 assumes all-adapters-compose.