#!/usr/bin/env bash
# run_rqgm.sh — run the EpochForge Lite scaffold (stub LLM, no API key needed).
# Produces archive.json + results.json. Uses a small budget so the single epoch
# boundary fires quickly. Real runs use --budget 80 --checkpoint 30 (spec defaults).
set -euo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

echo "Running RQGM scaffold (stub LLM, budget=12, checkpoint=5)..."
python3 search.py --mode rqgm --budget 12 --checkpoint 5
echo
echo "Generated: archive.json, results.json"
echo "Summary:   python3 plot.py"
echo "Baseline:  python3 search.py --mode hgm_h --budget 12"
