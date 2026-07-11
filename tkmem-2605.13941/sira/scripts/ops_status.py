#!/usr/bin/env python3
"""Local operations status check for TicketMind."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path


def main() -> None:
    checks = {
        "index_exists": Path("data/bm25_index.pkl").exists(),
        "df_store_exists": Path("data/df_store.json").exists(),
        "enriched_corpus_exists": Path("data/enriched_corpus.jsonl").exists(),
        "annotated_test_set_exists": Path("data/annotated_test_set.jsonl").exists(),
        "evolution_state_exists": Path("data/evolution_state.json").exists(),
        "simplemem_installed": importlib.util.find_spec("simplemem") is not None,
        "lancedb_installed": importlib.util.find_spec("lancedb") is not None,
    }
    print(json.dumps(checks, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
