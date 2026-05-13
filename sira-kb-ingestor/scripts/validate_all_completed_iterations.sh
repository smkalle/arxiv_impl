#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

"$ROOT_DIR/scripts/validate_iteration_1.sh"
"$ROOT_DIR/scripts/validate_iteration_2.sh"
"$ROOT_DIR/scripts/validate_iteration_3.sh"
"$ROOT_DIR/scripts/validate_iteration_4.sh"

echo "All completed iteration validators passed."
