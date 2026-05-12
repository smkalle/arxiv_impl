#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_5"
SAMPLE_OUT="$ARTIFACT_DIR/embedding_sample.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 5 OP-3 async embed validation"
echo "HOW: Verify embed operator files exist, generate embedding sample, run embed tests"
echo "RESULT: START"

required=(
  "$ROOT_DIR/kb_ingestor/ops/embed.py"
  "$ROOT_DIR/tests/test_embed.py"
  "$ROOT_DIR/RELEASE_NOTES_ITERATION_5.md"
)

for f in "${required[@]}"; do
  [[ -f "$f" ]] || { echo "missing: $f"; exit 1; }
  echo "ok: $f"
done

python3 - <<'PY' | tee "$SAMPLE_OUT"
import asyncio
import importlib

import numpy as np
import pyarrow as pa

from kb_ingestor.models import IngestConfig


class FakeEmbedder:
    def encode(self, chunks, convert_to_numpy=True, batch_size=128):
        out = []
        for text in chunks:
            base = float(len(text))
            out.append([base, base + 1.0, base + 2.0])
        return np.array(out, dtype=np.float32)


async def main() -> None:
    embed_mod = importlib.import_module("kb_ingestor.ops.embed")
    embed_mod._load_embedder = lambda _name: FakeEmbedder()
    table = pa.table({"id": ["1", "2"], "chunk": ["alpha", "beta"]})
    out = await embed_mod.embed(table, IngestConfig(batch_size=1, max_workers=2))
    print(out.schema)
    print(out.to_pylist())


asyncio.run(main())
PY

python3 -m pytest -q tests/test_embed.py | tee "$TEST_OUT"

grep -F -- "embedding: list<item: float>" "$SAMPLE_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: OP-3 embedding batches asynchronously, appends Arrow embedding vectors, and handles model/batch failures."
echo "iteration-5 validation passed" | tee -a "$TEST_OUT"
} | tee "$OUT_FILE"
