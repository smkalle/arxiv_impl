# RELEASE_NOTES_ITERATION_3.md

## Iteration 3 — OP-1 load/normalize

Date: 2026-05-12

## Delivered

- Implemented `kb_ingestor/ops/load.py` with source auto-detection and `source_type` override.
- Added Zendesk CSV load path via `pyarrow.csv.read_csv`.
- Added Jira JSON load path via `pyarrow.json.read_json` and nested field extraction.
- Added `pa.Table` input normalization path with canonical schema enforcement.
- Added null policy handling (`drop` and `raise`) for `description`.
- Added missing-column detection with `IngestSchemaError` and null-row errors via `IngestNullError`.

## Tests

- Added `tests/test_load.py` with:
  - `test_load_zendesk_csv`
  - `test_load_jira_json`
  - `test_load_arrow_table`
  - null-policy tests
  - missing-column error test

## Validation assets

- Validation script: `scripts/validate_iteration_3.sh`
- Visible artifacts:
  - `artifacts/iteration_3/normalized_sample.txt`
  - `artifacts/iteration_3/error_paths.txt`
  - `artifacts/iteration_3/test_output.txt`
