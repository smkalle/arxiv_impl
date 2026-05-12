#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_2"
SCHEMA_OUT="$ARTIFACT_DIR/schema_snapshot.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 2 models and errors validation"
echo "HOW: Verify model/error files exist, snapshot schema, run model/error tests"
echo "RESULT: START"

required=(
  "$ROOT_DIR/kb_ingestor/models.py"
  "$ROOT_DIR/kb_ingestor/errors.py"
  "$ROOT_DIR/tests/test_models.py"
  "$ROOT_DIR/tests/test_errors.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_2.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 -c "from kb_ingestor.models import CANONICAL_TICKET_SCHEMA; print(CANONICAL_TICKET_SCHEMA)" | tee "$SCHEMA_OUT"
python3 -m pytest -q tests/test_models.py tests/test_errors.py | tee "$TEST_OUT"

grep -F -- "id: string" "$SCHEMA_OUT" >/dev/null
grep -F -- "source: string" "$SCHEMA_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: Canonical schema, config defaults, and error taxonomy are implemented and tested."
echo "iteration-2 validation passed" | tee -a "$TEST_OUT"
} | tee "$OUT_FILE"
