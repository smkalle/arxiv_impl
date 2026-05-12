# RELEASE_v0.1.0.md

Release date: 2026-05-12

## Scope

- Completed implementation from iteration 0 through iteration 10.
- Delivered OP-1 through OP-4 pipeline components and async orchestration API.
- Delivered CLI (`run`, `validate`, `benchmark`) with exit-code mapping.
- Delivered fixture generation and integration tests.
- Delivered benchmark gate and human-validation workflow.

## Required artifacts

- `tickets.arrow`
- `index.faiss`
- `run_summary.json` with `embed_dim`

## Validation status

- All completed iteration validators pass via `scripts/validate_all_completed_iterations.sh`.
