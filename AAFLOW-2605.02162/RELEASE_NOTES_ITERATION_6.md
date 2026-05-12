# RELEASE_NOTES_ITERATION_6.md

## Iteration 6 — OP-4 upsert

Date: 2026-05-12

## Delivered

- Implemented `kb_ingestor/ops/upsert.py` with sequential upsert semantics.
- Added embedding extraction + float32 matrix conversion from Arrow list vectors.
- Added index-dimension checks and `EmbedDimMismatchError` handling.
- Added contiguous `faiss_id` assignment based on pre-add `index.ntotal`.
- Added atomic index write helper `write_index_atomic` with `FAISSWriteError` wrapping.
- Exported `upsert` in `kb_ingestor/ops/__init__.py`.

## Tests

- Added `tests/test_upsert.py`:
  - `test_faiss_id_contiguous`
  - `test_append_mode`
  - `test_dim_mismatch_raises`
  - `test_write_failure_path`
  - `test_embedding_dtype_cast_to_float32`
- Updated smoke imports in `tests/test_package_smoke.py`.

## Validation assets

- Validation script: `scripts/validate_iteration_6.sh`
- Visible artifacts:
  - `artifacts/iteration_6/faiss_id_verification.txt`
  - `artifacts/iteration_6/test_output.txt`
  - `artifacts/iteration_6/validation_output.txt`
