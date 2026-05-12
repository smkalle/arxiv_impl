# RELEASE_NOTES_ITERATION_8.md

## Iteration 8 — CLI completion

Date: 2026-05-12

## Delivered

- Completed `kb_ingestor/cli.py` command wiring for `run`, `validate`, and `benchmark`.
- Added error-to-exit-code mapping:
  - 1 input file not found
  - 2 schema failures
  - 3 embedding model failures
  - 4 FAISS write failures
  - 5 unexpected runtime errors
- Added config discovery and precedence:
  - `$PWD/.kb-ingestor.toml`
  - `$HOME/.config/kb-ingestor/config.toml`
  - CLI flags override config file values
- Added benchmark output serialization to `benchmark_results.json` and markdown table stdout.

## Tests

- Added and passed `tests/test_cli.py` covering success paths, exit codes, and config precedence.

## Validation assets

- Validation script: `scripts/validate_iteration_8.sh`
- Visible artifacts:
  - `artifacts/iteration_8/run_transcript.txt`
  - `artifacts/iteration_8/validate_transcript.txt`
  - `artifacts/iteration_8/benchmark_transcript.txt`
  - `artifacts/iteration_8/validation_output.txt`
