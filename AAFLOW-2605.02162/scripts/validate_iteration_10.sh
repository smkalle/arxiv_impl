#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_10"
TABLE_OUT="$ARTIFACT_DIR/benchmark_table.txt"
JSON_OUT="$ARTIFACT_DIR/benchmark_results.json"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 10 benchmark gate and release readiness validation"
echo "HOW: Generate fixtures, run benchmark CLI, verify markdown/json output and speedup threshold"
echo "RESULT: START"

make -C "$ROOT_DIR" fixtures
python3 -m kb_ingestor.cli benchmark --source "$ROOT_DIR/fixtures/zendesk_1k.csv" --rows 1000 --runs 1 --out "$ARTIFACT_DIR" | tee "$TABLE_OUT"

JSON_OUT="$JSON_OUT" python3 - <<'PY'
import json
import os
from pathlib import Path

path = Path(os.environ["JSON_OUT"])
data = json.loads(path.read_text(encoding="utf-8"))
speedup = float(data[0]["speedup_x"])
if speedup < 2.0:
    raise SystemExit(f"speedup gate failed: {speedup}")
print(f"speedup_gate_pass={speedup}")
PY

grep -F -- "| rows | baseline_s | arrow_s | speedup_x |" "$TABLE_OUT" >/dev/null
grep -F -- "speedup_x" "$JSON_OUT" >/dev/null
test -f "$ROOT_DIR/RELEASE_v0.1.0.md"

echo "RESULT: PASS"
echo "OVERALL SUMMARY: Benchmark gate passes at >=2.0x and release readiness artifacts are complete."
echo "iteration-10 validation passed"
} | tee "$OUT_FILE"
