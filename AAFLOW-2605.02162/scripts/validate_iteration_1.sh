#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_1"
HELP_OUT="$ARTIFACT_DIR/cli_help.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 1 scaffold validation"
echo "HOW: Verify scaffold files exist, run CLI help, run smoke tests"
echo "RESULT: START"

required=(
  "$ROOT_DIR/pyproject.toml"
  "$ROOT_DIR/kb_ingestor/__init__.py"
  "$ROOT_DIR/kb_ingestor/cli.py"
  "$ROOT_DIR/tests/test_package_smoke.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_1.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 -m kb_ingestor.cli --help | tee "$HELP_OUT"
python3 -m pytest -q tests/test_package_smoke.py | tee "$TEST_OUT"

grep -F -- "run" "$HELP_OUT" >/dev/null
grep -F -- "benchmark" "$HELP_OUT" >/dev/null
grep -F -- "validate" "$HELP_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: Iteration 1 scaffold is valid; CLI commands are wired and smoke tests passed."
echo "iteration-1 validation passed" | tee -a "$TEST_OUT"
} | tee "$OUT_FILE"
