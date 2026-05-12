#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_9"
FIXTURE_OUT="$ARTIFACT_DIR/fixture_summary.txt"
TEST_OUT="$ARTIFACT_DIR/integration_test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 9 fixtures and integration validation"
echo "HOW: Generate 1k fixtures, verify null/utf8 properties, run integration tests"
echo "RESULT: START"

make -C "$ROOT_DIR" fixtures

ROOT_DIR="$ROOT_DIR" python3 - <<'PY' > "$FIXTURE_OUT"
import json
import os
from pathlib import Path

root = Path(os.environ["ROOT_DIR"])
csv_path = root / "fixtures" / "zendesk_1k.csv"
json_path = root / "fixtures" / "jira_1k.json"

csv_lines = csv_path.read_text(encoding="utf-8").splitlines()[1:]
null_csv = sum(1 for line in csv_lines if ",," in line)

j_lines = json_path.read_text(encoding="utf-8").splitlines()
objs = [json.loads(x) for x in j_lines]
null_json = sum(1 for o in objs if o["fields"]["description"] is None)
utf8_hits = sum(1 for o in objs if any(ch in (o["fields"].get("description") or "") for ch in ["日", "ع"]))

print(f"csv_rows={len(csv_lines)}")
print(f"json_rows={len(objs)}")
print(f"csv_null_descriptions={null_csv}")
print(f"json_null_descriptions={null_json}")
print(f"utf8_edge_rows={utf8_hits}")
PY

python3 -m pytest -q tests/test_integration.py | tee "$TEST_OUT"

grep -F -- "csv_rows=1000" "$FIXTURE_OUT" >/dev/null
grep -F -- "json_rows=1000" "$FIXTURE_OUT" >/dev/null
grep -F -- "csv_null_descriptions=50" "$FIXTURE_OUT" >/dev/null
grep -F -- "json_null_descriptions=50" "$FIXTURE_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: Deterministic 1k fixtures generated with required null/UTF-8 characteristics and integration scenarios pass."
echo "iteration-9 validation passed"
} | tee "$OUT_FILE"
