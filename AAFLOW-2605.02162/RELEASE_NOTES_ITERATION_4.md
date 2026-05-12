# RELEASE_NOTES_ITERATION_4.md

## Iteration 4 — OP-2 chunk/preprocess

Date: 2026-05-12

## Delivered

- Implemented `kb_ingestor/ops/chunk.py` using Arrow compute only:
  - `pc.binary_join_element_wise` for `subject + " " + description`
  - `pc.utf8_slice_codeunits` for truncation to `max_chunk_chars`
  - `pc.utf8_length` + filter for `min_chunk_chars`
- Added `chunk` and `chunk_index` columns (`chunk_index` is `0` for all rows in v0.1).
- Exported `chunk` in `kb_ingestor/ops/__init__.py`.

## Tests

- Added `tests/test_chunk.py` covering:
  - vectorized chunk generation and truncation
  - min-length filtering
  - UTF-8 edge cases (Japanese/Arabic)
  - `chunk_index == 0`

## Validation assets

- Validation script: `scripts/validate_iteration_4.sh`
- Visible artifacts:
  - `artifacts/iteration_4/chunk_sample.txt`
  - `artifacts/iteration_4/test_output.txt`
  - `artifacts/iteration_4/validation_output.txt`
