# RELEASE_NOTES_ITERATION_5.md

## Iteration 5 — OP-3 async embed

Date: 2026-05-12

## Delivered

- Implemented async embedding operator in `kb_ingestor/ops/embed.py`.
- Added batch slicing + concurrent dispatch using `asyncio.gather`, `asyncio.Semaphore`, and `asyncio.to_thread`.
- Added embedding column as Arrow list float values (`embedding`).
- Added batch failure aggregation with `BatchProcessingError`.
- Added model load failure handling with `EmbedModelError`.
- Exported `embed` in `kb_ingestor/ops/__init__.py`.

## Tests

- Added `tests/test_embed.py`:
  - output shape and embedding column typing
  - row-order preservation
  - batch-size behavior
  - model load failure path
  - batch failure aggregation path
  - async concurrency path (`to_thread` usage)

## Validation assets

- Validation script: `scripts/validate_iteration_5.sh`
- Visible artifacts:
  - `artifacts/iteration_5/embedding_sample.txt`
  - `artifacts/iteration_5/test_output.txt`
  - `artifacts/iteration_5/validation_output.txt`
