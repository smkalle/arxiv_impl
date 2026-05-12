# RELEASE_NOTES_ITERATION_1.md

## Iteration 1 — Scaffold

Date: 2026-05-12

## Delivered

- Added package scaffold under `kb_ingestor/`.
- Added `pyproject.toml` with runtime and dev dependency sets.
- Added CLI skeleton with `run`, `benchmark`, and `validate` commands.
- Added smoke tests for public imports and CLI help output.
- Added Streamlit human-validation UI to inspect release notes, run iteration validators, and review visible artifacts.
- Added `scripts/validate_all_completed_iterations.sh` to run all completed iteration validators from `AGENTS.md`.

## Validation assets

- Validation script: `scripts/validate_iteration_1.sh`
- Visible artifact: `artifacts/iteration_1/cli_help.txt`
- UI entrypoint: `scripts/human_validation_ui.py`

## Notes

- Runtime behavior for pipeline operators is intentionally deferred to later iterations.
