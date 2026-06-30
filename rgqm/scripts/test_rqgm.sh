#!/usr/bin/env bash
# test_rqgm.sh — run the rgqm test suite (erasure invariant + archive round-trip).
set -u
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"
python3 -m pytest tests/ -q
