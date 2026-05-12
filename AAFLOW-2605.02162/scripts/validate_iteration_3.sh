#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_3"
SAMPLE_OUT="$ARTIFACT_DIR/normalized_sample.txt"
ERROR_OUT="$ARTIFACT_DIR/error_paths.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 3 OP-1 load/normalize validation"
echo "HOW: Verify loader files exist, generate normalized sample, trigger error paths, run load tests"
echo "RESULT: START"

required=(
  "$ROOT_DIR/kb_ingestor/ops/load.py"
  "$ROOT_DIR/tests/test_load.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_3.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 - <<'PY' | tee "$SAMPLE_OUT"
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_ingestor.models import IngestConfig
from kb_ingestor.ops.load import load

with TemporaryDirectory() as d:
    p = Path(d) / "tickets.csv"
    p.write_text(
        "id,subject,description,status,created_at,tags\n"
        "1,Login issue,Cannot sign in,open,2026-01-01T10:00:00Z,auth\n",
        encoding="utf-8",
    )
    table = load(p, IngestConfig())
    print(table.schema)
    print(table.to_pylist())
PY

python3 - <<'PY' | tee "$ERROR_OUT"
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_ingestor.errors import IngestNullError, IngestSchemaError
from kb_ingestor.models import IngestConfig
from kb_ingestor.ops.load import load

with TemporaryDirectory() as d:
    bad = Path(d) / "bad.csv"
    bad.write_text("id,subject\n1,only\n", encoding="utf-8")
    try:
        load(bad, IngestConfig())
    except IngestSchemaError as exc:
        print(f"schema_error={exc}")

    nulls = Path(d) / "nulls.csv"
    nulls.write_text(
        "id,subject,description,status\n"
        "1,ok,hello,open\n"
        "2,bad,,open\n",
        encoding="utf-8",
    )
    try:
        load(nulls, IngestConfig(null_policy="raise"))
    except IngestNullError as exc:
        print(f"null_error={exc}")
PY

python3 -m pytest -q tests/test_load.py | tee "$TEST_OUT"

grep -F -- "source: string" "$SAMPLE_OUT" >/dev/null
grep -F -- "schema_error=" "$ERROR_OUT" >/dev/null
grep -F -- "null_error=" "$ERROR_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: OP-1 normalizes CSV/JSON/Arrow inputs and enforces schema/null policies correctly."
echo "iteration-3 validation passed" | tee -a "$TEST_OUT"
} | tee "$OUT_FILE"
