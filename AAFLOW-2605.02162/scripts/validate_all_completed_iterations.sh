#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_FILE="$ROOT_DIR/AGENTS.md"
OUT_DIR="$ROOT_DIR/artifacts"
OUT_FILE="$OUT_DIR/validation_all_completed_iterations.txt"

mkdir -p "$OUT_DIR"

mapfile -t scripts_to_run < <(
  # Checklist-driven discovery: when an iteration is marked complete in AGENTS.md,
  # its validation script line is checked [x] and this runner will include it.
  grep -oE 'scripts/validate_iteration_[0-9]+\.sh' "$AGENTS_FILE" | awk '!seen[$0]++'
)

{
  echo "[all-iterations] validation started"
  echo "date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "root=$ROOT_DIR"

  ran=0
  for rel_script in "${scripts_to_run[@]}"; do
    if grep -F -- "- [x] **Validation script:** \`$rel_script\`" "$AGENTS_FILE" >/dev/null 2>&1; then
      echo "running: $rel_script"
      "$ROOT_DIR/$rel_script"
      ran=$((ran + 1))
    fi
  done

  echo "completed_validation_scripts=$ran"
  echo "[all-iterations] validation passed"
} | tee "$OUT_FILE"
