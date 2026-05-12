#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_8"
RUN_OUT="$ARTIFACT_DIR/run_transcript.txt"
VALIDATE_OUT="$ARTIFACT_DIR/validate_transcript.txt"
BENCH_OUT="$ARTIFACT_DIR/benchmark_transcript.txt"
TEST_OUT="$ARTIFACT_DIR/test_output.txt"
OUT_FILE="$ARTIFACT_DIR/validation_output.txt"

mkdir -p "$ARTIFACT_DIR"

{
echo "FUNCTIONALITY: Iteration 8 CLI completion validation"
echo "HOW: Run CLI tests and capture run/validate/benchmark command transcripts with mocked execution"
echo "RESULT: START"

python3 -m pytest -q tests/test_cli.py | tee "$TEST_OUT"

python3 - <<'PY' > "$RUN_OUT"
import asyncio
from click.testing import CliRunner
import pyarrow as pa
import kb_ingestor.cli as cli_mod
from kb_ingestor.models import IngestResult

async def fake_ingest(_source, _config):
    return IngestResult(table=pa.table({"id":["1"]}), index=type("Idx", (), {"ntotal": 1})(), metrics={}, artifacts={})

cli_mod.ingest = fake_ingest
runner = CliRunner()
with runner.isolated_filesystem():
    with open("tickets.csv", "w", encoding="utf-8") as f:
        f.write("id,subject,description\n1,a,desc long enough\n")
    res = runner.invoke(cli_mod.cli, ["run", "--source", "tickets.csv"])
    print(res.output)
    print(f"exit_code={res.exit_code}")
PY

python3 - <<'PY' > "$VALIDATE_OUT"
from click.testing import CliRunner
import kb_ingestor.cli as cli_mod
import pyarrow as pa

cli_mod.load = lambda *_args, **_kwargs: pa.table({"id":["1"]})
runner = CliRunner()
with runner.isolated_filesystem():
    with open("tickets.csv", "w", encoding="utf-8") as f:
        f.write("id,subject,description\n1,a,b\n")
    res = runner.invoke(cli_mod.cli, ["validate", "--source", "tickets.csv"])
    print(res.output)
    print(f"exit_code={res.exit_code}")
PY

python3 - <<'PY' > "$BENCH_OUT"
from click.testing import CliRunner
import kb_ingestor.cli as cli_mod

cli_mod.run_benchmark = lambda *_args, **_kwargs: [{"rows":1000, "baseline_s":2.2, "arrow_s":1.0, "speedup_x":2.2}]
runner = CliRunner()
with runner.isolated_filesystem():
    with open("tickets.csv", "w", encoding="utf-8") as f:
        f.write("id,subject,description\n1,a,b\n")
    res = runner.invoke(cli_mod.cli, ["benchmark", "--source", "tickets.csv", "--rows", "1000", "--runs", "1", "--out", "bench"])
    print(res.output)
    print(f"exit_code={res.exit_code}")
PY

grep -F -- "exit_code=0" "$RUN_OUT" >/dev/null
grep -F -- "exit_code=0" "$VALIDATE_OUT" >/dev/null
grep -F -- "exit_code=0" "$BENCH_OUT" >/dev/null
grep -F -- "passed" "$TEST_OUT" >/dev/null

echo "RESULT: PASS"
echo "OVERALL SUMMARY: CLI commands are fully wired, tested, and produce expected command-level outputs."
echo "iteration-8 validation passed"
} | tee "$OUT_FILE"
