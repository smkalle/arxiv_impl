#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_6"
VERIFY_OUT="$ARTIFACT_DIR/faiss_id_verification.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 6 OP-4 upsert validation"
echo "HOW: Verify upsert files exist, run faiss_id continuity demo, run upsert tests"
echo "RESULT: START"

required=(
  "$ROOT_DIR/kb_ingestor/ops/upsert.py"
  "$ROOT_DIR/tests/test_upsert.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_6.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 - <<'PY' | tee "$VERIFY_OUT"
import pyarrow as pa

from kb_ingestor.ops.upsert import upsert


class FakeIndex:
    def __init__(self, dim: int):
        self.d = dim
        self.ntotal = 0

    def add(self, embeddings):
        self.ntotal += embeddings.shape[0]


index = FakeIndex(3)
table = pa.table(
    {
        "id": ["a", "b", "c"],
        "embedding": [[1.0, 0.0, 0.0], [0.0, 1.0, 0.0], [0.0, 0.0, 1.0]],
    }
)
out, index = upsert(table, index)
ids = out.column("faiss_id").to_pylist()
print(f"faiss_id={ids}")
print(f"index_ntotal={index.ntotal}")
print(f"contiguous={ids == [0, 1, 2]}")
PY

python3 -m pytest -q tests/test_upsert.py tests/test_package_smoke.py | tee "$TEST_OUT"

grep -F -- "contiguous=True" "$VERIFY_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: OP-4 assigns contiguous faiss_id values, enforces dim compatibility, and supports atomic write error handling."
echo "iteration-6 validation passed" | tee -a "$TEST_OUT"
} | tee "$OUT_FILE"
