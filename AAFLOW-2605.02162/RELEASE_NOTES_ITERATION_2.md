# RELEASE_NOTES_ITERATION_2.md

## Iteration 2 — Models and errors

Date: 2026-05-12

## Delivered

- Implemented canonical 7-column Arrow schema constant in `kb_ingestor/models.py`.
- Expanded `IngestConfig` with spec-aligned defaults and options.
- Finalized `IngestResult` dataclass defaults.
- Added full error taxonomy in `kb_ingestor/errors.py`:
  - `IngestSchemaError`
  - `IngestNullError`
  - `EmbedModelError`
  - `EmbedDimMismatchError`
  - `FAISSWriteError`
  - `BatchProcessingError`
- Exported schema and all error classes from package surface in `kb_ingestor/__init__.py`.
- Added unit tests for models/schema/defaults and errors.

## Validation assets

- Validation script: `scripts/validate_iteration_2.sh`
- Visible artifacts:
  - `artifacts/iteration_2/schema_snapshot.txt`
  - `artifacts/iteration_2/test_output.txt`

## Human validation UI

- `scripts/human_validation_ui.py` updated to show selected iteration checklist lines from `AGENTS.md`.
- `scripts/validate_all_completed_iterations.sh` remains the aggregate runner and now executes iteration 2 after checklist completion.
