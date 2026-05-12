#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_7"
LIST_OUT="$ARTIFACT_DIR/artifact_listing.txt"
SUMMARY_OUT="$ARTIFACT_DIR/run_summary_sample.json"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 7 API orchestration and artifact writer validation"
echo "HOW: Verify API files exist, run API tests, execute sample ingest, inspect generated artifacts"
echo "RESULT: START"

required=(
  "$ROOT_DIR/kb_ingestor/api.py"
  "$ROOT_DIR/tests/test_api.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_7.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 -m pytest -q tests/test_api.py tests/test_package_smoke.py | tee "$TEST_OUT"

LIST_OUT="$LIST_OUT" SUMMARY_OUT="$SUMMARY_OUT" python3 - <<'PY'
import asyncio
import importlib
import json
import os
from pathlib import Path
from tempfile import TemporaryDirectory

from kb_ingestor.api import ingest
from kb_ingestor.models import IngestConfig


class FakeEmbedder:
    def encode(self, chunks, convert_to_numpy=True, batch_size=128):
        return [[float(len(c)), float(len(c))+1.0, float(len(c))+2.0] for c in chunks]


async def main() -> None:
    embed_mod = importlib.import_module("kb_ingestor.ops.embed")
    embed_mod._load_embedder = lambda _name: FakeEmbedder()
    with TemporaryDirectory() as d:
        root = Path(d)
        src = root / "tickets.csv"
        out = root / "out"
        src.write_text(
            "id,subject,description,status,created_at,tags\n"
            "1,Login issue,Cannot sign in,open,2026-01-01T10:00:00Z,auth\n"
            "2,UI bug,Button overlaps text,open,2026-01-02T10:00:00Z,ui\n",
            encoding="utf-8",
        )
        await ingest(src, IngestConfig(output_path=out))
        items = sorted(p.name for p in out.iterdir())
        Path(os.environ["LIST_OUT"]).write_text("\n".join(items), encoding="utf-8")
        summary = json.loads((out / "run_summary.json").read_text(encoding="utf-8"))
        Path(os.environ["SUMMARY_OUT"]).write_text(json.dumps(summary, indent=2), encoding="utf-8")


asyncio.run(main())
PY

grep -F -- "tickets.arrow" "$LIST_OUT" >/dev/null
grep -F -- "index.faiss" "$LIST_OUT" >/dev/null
grep -F -- "run_summary.json" "$LIST_OUT" >/dev/null
grep -F -- '"embed_dim"' "$SUMMARY_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: API orchestration runs all operators in order and writes reloadable output artifacts with run_summary embed_dim metadata."
echo "iteration-7 validation passed"
} | tee "$OUT_FILE"
