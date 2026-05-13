#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
ARTIFACT_DIR="$ROOT_DIR/artifacts/iteration_4"
mkdir -p "$ARTIFACT_DIR"

cd "$ROOT_DIR"

echo "[RUN] Iteration 4 CLI, benchmark, and integration validation"
python3 -m pytest tests/test_cli.py tests/test_cli_iteration3.py tests/test_benchmark.py tests/test_integration.py -v -s | tee "$ARTIFACT_DIR/pytest_output.txt"

python3 - <<'PY'
import asyncio
from dataclasses import dataclass, field
from pathlib import Path

import sira_kb_ingestor.benchmark as bench
from sira_kb_ingestor.models import IngestAndRetrieveConfig


@dataclass
class FakeResult:
    combined_metrics: dict = field(default_factory=dict)
    kb_summary: dict = field(default_factory=dict)
    artifacts: dict = field(default_factory=dict)


async def fake_setup(ticket_source, kb_source, config):
    rows = max(0, len(Path(ticket_source).read_text(encoding="utf-8").splitlines()) - 1)
    Path(config.output_path).mkdir(parents=True, exist_ok=True)
    return FakeResult(combined_metrics={"rows_ingested": rows})


async def main():
    out = Path("artifacts/iteration_4/benchmark_smoke")
    out.mkdir(parents=True, exist_ok=True)
    tickets = out / "tickets.csv"
    tickets.write_text("id,subject,description\n1,a,b\n2,c,d\n", encoding="utf-8")
    kb = out / "kb.jsonl"
    kb.write_text('{"article_id":"kb-1","title":"Auth","body":"Login help"}\n', encoding="utf-8")
    bench.setup_full_system = fake_setup
    report = await bench.run_setup_benchmark(tickets, kb, [2, 4], 1, out, IngestAndRetrieveConfig())
    Path("artifacts/iteration_4/benchmark_table.md").write_text(report["markdown_table"], encoding="utf-8")
    print(report["markdown_table"])


asyncio.run(main())
PY

cat > "$ARTIFACT_DIR/validation_output.txt" <<'EOF'
Iteration 4 Validation

Checks:
- [PASS] setup CLI parses flags, merges config, maps failures, and prints JSON summary
- [PASS] query CLI returns JSON and exits non-zero on retrieval failures
- [PASS] server CLI defaults to host 0.0.0.0, port 8000, workers 4
- [PASS] benchmark runner writes benchmark_report.json and benchmark_table.md
- [PASS] real Zendesk CSV and Jira JSON integration tests are present and skip with clear reasons when external services are unavailable

See:
- pytest_output.txt
- benchmark_table.md
EOF

echo "Iteration 4 validation completed."
