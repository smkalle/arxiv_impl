# TicketMind Iterative Implementation Plan

This plan turns `ticketmind-spec.md` into human-verifiable increments. Each iteration must start only after its start checklist is true and must finish only after both automated signoff testing and visible human validation pass.

## Iteration 0: Repository Foundation

**Goal:** Create the runnable project skeleton under `sira/`.

**Start Checklist**
- [x] Confirm target runtime is UserLAnd Ubuntu with `python3` available.
- [x] Confirm no Docker requirement; all commands run from `sira/`.
- [x] Create `sira/src`, `sira/tests`, `sira/scripts`, and `sira/data`.
- [x] Add `requirements.txt` with FastAPI, pytest, rank-bm25, nltk, requests, and runtime dependencies.

**Signoff Testing Checklist**
- [x] `python3 -m pytest tests/` runs, even if only smoke tests exist.
- [x] `python3 -c "import src"` works from `sira/`.
- [x] `python3 -m compileall src scripts` completes without syntax errors.

**Visible Changes for Human Validation**
- [x] Reviewer can see the directory layout in `sira/`.
- [x] README or command notes show setup and local run commands.
- [x] Generated artifacts are excluded from version control.

## Iteration 1: Corpus Index and Plain BM25 Retrieval

**Goal:** Load KB JSONL, tokenize consistently, build a BM25 index, and retrieve baseline results.

**Start Checklist**
- [x] `data/kb_corpus.jsonl` exists with stable `id`, `title`, and `body` fields.
- [x] Tokenization rules are accepted: lowercase, min length 2, at least one alphanumeric character.
- [x] Decide where generated `bm25_index.pkl` and `df_store.json` are written.

**Signoff Testing Checklist**
- [x] `python3 src/index.py data/kb_corpus.jsonl --output data/bm25_index.pkl` writes the index.
- [x] `python3 scripts/query.py "app keeps crashing"` returns top-k KB results.
- [x] Unit tests cover tokenization, index persistence, and plain retrieval ranking.

**Visible Changes for Human Validation**
- [x] Human can run one query and inspect returned KB IDs, titles, scores, and snippets.
- [x] `data/df_store.json` is readable and contains document-frequency counts.
- [x] Baseline retrieval examples are documented for at least three support-ticket phrasings.

## Iteration 2: Offline KB Enrichment

**Goal:** Add LLM-generated customer-language enrichment terms to KB articles.

**Start Checklist**
- [x] Ollama or configured API backend is reachable.
- [x] `OLLAMA_HOST` and `OLLAMA_MODEL` defaults are documented.
- [x] Enrichment output schema includes `enriched_terms`, `enriched_body`, `enriched_at`, and `last_updated`.

**Signoff Testing Checklist**
- [x] `python3 src/enrich.py --input data/kb_corpus.jsonl --output data/enriched_corpus.jsonl` processes a sample corpus.
- [x] Tests mock the LLM and verify parsing rejects original-text duplicates, mixed alphanumerics, and suspicious long single tokens.
- [x] Re-running enrichment skips articles where `enriched_at >= last_updated`.

**Visible Changes for Human Validation**
- [x] Human can open enriched JSONL and compare each original article to generated customer-language terms.
- [x] Logs show skipped, enriched, and failed article counts.
- [x] At least 10 enriched articles are manually spot-checked for useful vocabulary bridging.

## Iteration 3: Online Sketch Generation and DF Validation

**Goal:** Generate ticket-time KB-jargon sketches and filter hallucinated or overly broad terms.

**Start Checklist**
- [x] `df_store.json` exists from the current corpus.
- [x] Default `tau=0.01` and sketch temperature are agreed.
- [x] Failure behavior is defined: fall back to plain BM25 if sketch generation fails or times out.

**Signoff Testing Checklist**
- [x] Unit tests cover `validate_sketch_terms()` for accepted, rejected, absent, and over-threshold terms.
- [x] Sketch tests mock the LLM and assert 8-12 term parsing behavior.
- [x] Failure-path tests confirm `fallback_used=True` and no exception leaks to the caller.

**Visible Changes for Human Validation**
- [x] Query trace shows generated terms, accepted terms, rejected terms, and hallucination rate.
- [x] Human can verify rejected terms explain why they failed DF validation.
- [x] Example query demonstrates vocabulary bridge, such as "app crashes on login" to authentication/session jargon.

## Iteration 4: Weighted TKMEM/EvolveMem-Style Retrieval

**Goal:** Combine original ticket BM25 score with weighted validated-sketch BM25 score as a local approximation of TKMEM/EvolveMem retrieval-policy evolution.

**Start Checklist**
- [x] Plain retrieval and sketch validation are stable.
- [x] Default weight `w=1.5` is documented and CLI-overridable.
- [x] Index loading contract is clear: `load_index()` before retrieval or `_set_index()` in tests.

**Signoff Testing Checklist**
- [x] `python3 scripts/query.py --evolved "My app keeps crashing on login"` returns scored results with trace data.
- [x] Tests cover score fusion: `BM25(orig_tokens) + w * BM25(validated_sketch_tokens)`.
- [x] Tests verify fallback to plain BM25 when no valid sketch terms remain.

**Visible Changes for Human Validation**
- [x] CLI output clearly separates plain tokens, sketch terms, weighted scores, and final ranking.
- [x] Side-by-side examples show when evolved retrieval improves rank versus baseline BM25.
- [x] Reviewer can tune `--tau` and `--weight` and see ranking changes.

## Iteration 5: Evaluation Harness and Annotated Test Set

**Goal:** Measure baseline and TKMEM evolved retrieval quality on ticket-to-KB annotations.

**Start Checklist**
- [x] Define annotation JSONL schema with ticket text and ground-truth KB ID(s).
- [x] Replace placeholder test data with hand-reviewed examples before final acceptance.
- [x] Agree metric definitions for F1@5, hit@5, and latency percentiles.

**Signoff Testing Checklist**
- [x] Evaluation script runs baseline BM25 and evolved retrieval on the same test set.
- [x] Output includes F1@5, hit@5, mean latency, and P95 latency.
- [x] Tests cover metric calculation with deterministic fixture rankings.

**Visible Changes for Human Validation**
- [x] Human can inspect failed queries with expected KB IDs and retrieved KB IDs.
- [x] Evaluation summary is saved as a timestamped report.
- [x] Baseline target is recorded; acceptance requires post-evolution F1@5 >= 0.55.

## Iteration 6: FastAPI Retrieval API

**Goal:** Expose retrieval through local HTTP endpoints for the dashboard and automation.

**Start Checklist**
- [x] API schemas for `/query` and `/health` match `ticketmind-spec.md`.
- [x] Decide local port, default `8001`.
- [x] Existing CLI retrieval path is reusable without duplicating ranking logic.

**Signoff Testing Checklist**
- [x] `uvicorn src.ticket_api:app --reload --port 8001` starts locally.
- [x] `curl -sS http://127.0.0.1:8001/health` returns healthy status and config version.
- [x] API tests cover success, invalid payloads, missing index, and sketch fallback.

**Visible Changes for Human Validation**
- [x] Human can POST a ticket and receive top-k KB results as JSON.
- [x] Response includes latency, fallback flag, and audit trace.
- [x] Errors are readable and actionable, not raw stack traces.

## Iteration 7: Admin and Enrichment Monitor UI

**Goal:** Provide a browser interface for KB browsing, query inspection, and enrichment monitoring.

**Start Checklist**
- [x] Confirm whether the current static `ticketmind-dashboard.html` is prototype-only or source for templates.
- [x] API endpoints needed by dashboard are available or stubbed.
- [x] Static asset and template paths are relative to the `sira/` working directory.

**Signoff Testing Checklist**
- [x] `uvicorn src.enrich_ui:app --reload` starts without path errors.
- [x] UI tests or smoke checks cover dashboard home, KB list, query inspector, and enrichment status.
- [x] Browser console check not run because Playwright/browser tooling is not installed; HTTP-rendered page checks passed.

**Visible Changes for Human Validation**
- [x] Human can open the dashboard and run a query from the Query Inspector.
- [x] UI displays TKMEM trace, accepted/rejected terms, and ranked KB results.
- [x] KB page shows enrichment counts; system/evolution pages show runtime status.

## Iteration 8: SimpleMem, Cross-Session Memory, and Evolution

**Goal:** Integrate SimpleMem/EvolveMem features from the full TicketMind v1.0 spec.

**Start Checklist**
- [x] SimpleMem and LanceDB dependency status is detected; compatibility mode is used when absent.
- [x] `df -T data` was checked and recorded for the local data path.
- [x] Dev set contains 10 annotated tickets for local optimization smoke testing.

**Signoff Testing Checklist**
- [x] Local compatibility ingestor/index creates lexical DF/BM25 artifacts without LanceDB dependency errors.
- [x] Compatibility evolution completes 7 rounds and writes evolved config/state.
- [x] Cross-session tests cover `/session/start`, `/session/record`, and `/session/end`.
- [x] Compatibility post-evolution F1@5 improves by at least 15% relative and reaches target.

**Visible Changes for Human Validation**
- [x] Dashboard Evolution Monitor shows round history, accepted strategies, and rejected strategies.
- [x] Session API records prior customer context for later retrieval integration.
- [x] Query Inspector shows baseline token trace plus TKMEM evolved retrieval behavior.

## Iteration 9: Local Operations and Handoff

**Goal:** Make the system restartable, observable, and handoff-ready on UserLAnd Ubuntu.

**Start Checklist**
- [x] Service entrypoints are stable for API, dashboard, enrichment/indexing, and evolve-worker compatibility mode.
- [x] Runtime data directories and generated artifacts are documented.
- [x] Acceptance test set and representative smoke queries are finalized.

**Signoff Testing Checklist**
- [x] systemd user service templates are provided for API, dashboard, and evolve-worker.
- [x] Local uvicorn service starts were verified for API and dashboard.
- [x] Full smoke test runs after service start: health, query, dashboard query trace, and 10-query regression.
- [x] Acceptance report confirms F1@5, P95 latency, evolution gain, and dashboard HTTP availability gates.

**Visible Changes for Human Validation**
- [x] Human can restart local services using documented uvicorn/systemd-template commands.
- [x] Dashboard System Health shows index/corpus status and optional dependency status.
- [x] Handoff notes identify known limitations, generated artifacts, and how to rebuild indexes.

## Completion Rules

- Do not advance an iteration unless every start checklist item is true or explicitly deferred with an owner.
- Do not sign off an iteration unless automated tests and human-visible validation both pass.
- Keep generated indexes, enriched corpora, reports, and logs reproducible from committed source and documented commands.
- Update this file when scope changes; `ticketmind-spec.md` remains the product contract, while this file is the execution checklist.
