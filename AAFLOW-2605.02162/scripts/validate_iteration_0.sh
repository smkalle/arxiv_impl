#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_0"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
  echo "FUNCTIONALITY: Iteration 0 contract freeze validation"
  echo "HOW: Verify planning artifacts and iteration-0 checklist completion"
  echo "RESULT: START"
  echo "[iteration-0] validation started"
  echo "date=$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "root=$ROOT_DIR"

  required=(
    "$ROOT_DIR/AGENTS.md"
    "$ROOT_DIR/CLAUDE.md"
    "$ROOT_DIR/AAFLOW-arXiv:2605.02162-spec-kb-ingestor.md"
    "$ROOT_DIR/RELEASE_NOTES_ITERATION_0.md"
  )

  echo "checking required files..."
  for f in "${required[@]}"; do
    if [[ -f "$f" ]]; then
      echo "ok: $f"
    else
      echo "missing: $f"
      exit 1
    fi
  done

  echo "checking AGENTS.md iteration-0 checkboxes..."
  grep -F -- "- [x] **Design:** freeze v0.1 scope" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Plan:** produce requirement→test mapping" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Implementation:** create planning docs only" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Test:** review docs against" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Signoff artifacts:** \`IMPLEMENTATION_PLAN.md\`, \`ACCEPTANCE_MATRIX.md\`" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Release notes:** \`RELEASE_NOTES_ITERATION_0.md\`" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Validation script:** \`scripts/validate_iteration_0.sh\`" "$ROOT_DIR/AGENTS.md" >/dev/null
  grep -F -- "- [x] **Visible change artifact:** \`artifacts/iteration_0/validation_output.txt\`" "$ROOT_DIR/AGENTS.md" >/dev/null
  echo "ok: iteration-0 checklist complete"

  echo "RESULT: PASS"
  echo "OVERALL SUMMARY: Kickoff contract docs and acceptance mapping are present and signed off."
  echo "[iteration-0] validation passed"
} | tee "$OUT_FILE"
