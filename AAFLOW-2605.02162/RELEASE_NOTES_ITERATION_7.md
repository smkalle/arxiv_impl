# RELEASE_NOTES_ITERATION_7.md

## Iteration 7 — Orchestration API and artifact writer

Date: 2026-05-12

## Delivered

- Implemented `kb_ingestor/api.py` async orchestration via OP chain:
  - `load` -> `chunk` -> `embed` -> `upsert`
- Added artifact writing when `config.output_path` is set:
  - `tickets.arrow` (Arrow IPC file)
  - `index.faiss` (atomic write helper)
  - `run_summary.json` including `embed_dim`
- Added metrics capture in `IngestResult.metrics` (`elapsed_s`, `rows_ingested`, `batches`, `throughput_rps`).
- Preserved in-memory mode behavior (`output_path=None` => no artifact writes).

## Tests

- Added `tests/test_api.py` with end-to-end API coverage for CSV, JSON, in-memory mode, artifact writes, run-summary key checks, and artifact reloadability.

## Validation assets

- Validation script: `scripts/validate_iteration_7.sh`
- Visible artifacts:
  - `artifacts/iteration_7/artifact_listing.txt`
  - `artifacts/iteration_7/run_summary_sample.json`
  - `artifacts/iteration_7/test_output.txt`
  - `artifacts/iteration_7/validation_output.txt`
