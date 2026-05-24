"""
CLI entry point for loop_runner. Invoked by evolvemem-runner.service
and by `python -m evolvemem_runner`.

Usage:
  python evolvemem_runner.py                  # full L1→L2→L3→L4 run
  python evolvemem_runner.py --only L3        # only L3
  python evolvemem_runner.py --from L2        # start from L2
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

import config as cfg
from loops.loop_runner import run_all_loops


class _Settings:
    simplemem_use_stub = cfg.SIMPLEMEM_USE_STUB
    lancedb_uri = str(cfg.LANCEDB_DIR)
    diagnosis_llm_provider = cfg.DIAGNOSIS_LLM_PROVIDER
    diagnosis_llm_model = cfg.ANTHROPIC_MODEL
    anthropic_api_key = cfg.ANTHROPIC_API_KEY
    ollama_host = cfg.OLLAMA_URL
    ollama_model = cfg.OLLAMA_MODEL
    data_dir = str(cfg.DATA_DIR)


def main() -> None:
    parser = argparse.ArgumentParser(description="EvolveMem AutoResearch Loop Runner")
    parser.add_argument("--from", dest="start_from", default="L1",
                        choices=["L1", "L2", "L3", "L4"],
                        help="Start from this loop (skip earlier ones)")
    parser.add_argument("--only", dest="only", default=None,
                        choices=["L1", "L2", "L3", "L4"],
                        help="Run only this specific loop")
    args = parser.parse_args()

    cfg.preflight(require_ext4=False)

    settings = _Settings()
    results = run_all_loops(
        settings=settings,
        start_from=args.start_from,
        only=args.only,
    )

    print("\n── AutoResearch Summary ──")
    for lid, result in results.items():
        delta = result.best_fitness - result.baseline_fitness
        print(
            f"  {lid}: {result.baseline_fitness:.4f} → {result.best_fitness:.4f} "
            f"(+{delta:.4f}) [{result.rounds_run} rounds]"
        )
    print("\nDone.")


if __name__ == "__main__":
    main()
