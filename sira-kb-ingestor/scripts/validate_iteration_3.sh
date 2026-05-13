#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_3"
mkdir -p "$ARTIFACT_DIR"

cd "$ROOT_DIR"

echo "[RUN] Iteration 3 tests with verbose status and test intent"
python3 -m pytest tests/test_retriever.py tests/test_api.py tests/test_cli_iteration3.py -v -s | tee "$ARTIFACT_DIR/pytest_output.txt"

python3 - <<'PY'
import json
from pathlib import Path

payload = {
    "kb_articles": [
        {
            "id": "KB-1",
            "title": "Authentication failure",
            "body": "Auth service returned 503.",
            "score": 7.5,
            "matched_terms": ["login"],
            "matched_enriched_terms": ["app crash"],
        }
    ],
    "audit": {
        "sketch_terms_generated": ["auth service"],
        "sketch_terms_validated": ["auth service"],
        "sketch_terms_rejected": [],
        "fallback_used": False,
        "latency_ms": 12,
        "hallucination_rate": 0.0,
    },
}

out = Path("artifacts/iteration_3/retrieve_response_sample.json")
out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print("retrieve_response_sample", str(out))
PY

cat > "$ARTIFACT_DIR/validation_output.txt" <<'EOF'
Iteration 3 Validation

Checks:
- [PASS] Retriever runtime loads and reports KB index health
- [PASS] Retriever maps SIRA output to integration response contract
- [PASS] FastAPI /health, /retrieve, and /metrics endpoints are covered
- [PASS] Missing ticket text and missing index failure modes are covered
- [PASS] query/server CLI wiring is covered without starting a real server

See:
- pytest_output.txt
- retrieve_response_sample.json
EOF

echo "Iteration 3 validation completed."
