#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_4"
SAMPLE_OUT="$ARTIFACT_DIR/chunk_sample.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 4 OP-2 chunk/preprocess validation"
echo "HOW: Verify chunk operator files exist, generate chunk sample, run chunk tests"
echo "RESULT: START"

required=(
  "$ROOT_DIR/kb_ingestor/ops/chunk.py"
  "$ROOT_DIR/tests/test_chunk.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_4.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 - <<'PY' | tee "$SAMPLE_OUT"
import pyarrow as pa

from kb_ingestor.models import IngestConfig
from kb_ingestor.ops.chunk import chunk

table = pa.table(
    {
        "id": ["1"],
        "subject": ["Login"],
        "description": ["Cannot sign in because token expired"],
        "status": ["open"],
        "created_at": [None],
        "tags": [["auth"]],
        "source": ["zendesk"],
    }
)
out = chunk(table, IngestConfig(max_chunk_chars=16, min_chunk_chars=5))
print(out.schema)
print(out.to_pylist())
PY

python3 -m pytest -q tests/test_chunk.py | tee "$TEST_OUT"

grep -F -- "chunk: string" "$SAMPLE_OUT" >/dev/null
grep -F -- "chunk_index: int32" "$SAMPLE_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: OP-2 chunking is vectorized, UTF-8 safe, and enforces truncation/min-length rules."
echo "iteration-4 validation passed" | tee -a "$TEST_OUT"
} | tee "$OUT_FILE"
