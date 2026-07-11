#!/usr/bin/env python3
"""Run a plain BM25 query against the local KB corpus."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.index import build_and_save  # noqa: E402
from src.retrieve import evolved_retrieve, load_index, retrieve  # noqa: E402


def ensure_index(corpus_path: Path, index_path: Path) -> None:
    if index_path.exists():
        return
    print(f"Index not found at {index_path}; building from {corpus_path}.")
    build_and_save(corpus_path, index_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Query TicketMind KB with plain BM25.")
    parser.add_argument("query", help="Support ticket text to search for")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to show")
    parser.add_argument("--corpus", default="data/kb_corpus.jsonl", help="KB corpus JSONL path")
    parser.add_argument("--index", default="data/bm25_index.pkl", help="BM25 index pickle path")
    parser.add_argument("--evolved", action="store_true", help="Use TKMEM/EvolveMem-style evolved retrieval with sketch trace")
    parser.add_argument("--sira", action="store_true", help="Backward-compatible alias for --evolved")
    parser.add_argument("--tau", type=float, default=0.01, help="DF validation threshold")
    parser.add_argument("--weight", type=float, default=1.5, help="Sketch score weight")
    args = parser.parse_args()

    corpus_path = Path(args.corpus)
    index_path = Path(args.index)
    ensure_index(corpus_path, index_path)
    load_index(index_path)

    if args.evolved or args.sira:
        payload = evolved_retrieve(args.query, top_k=args.top_k, tau=args.tau, weight=args.weight)
        results = payload["results"]
        trace = payload["trace"]
        print(f"mode=evolved fallback_used={payload['fallback_used']}")
        print(f"plain_tokens={trace['plain_tokens']}")
        print(f"generated_terms={trace['generated_terms']}")
        print(f"accepted_terms={trace['accepted_terms']}")
        print(f"rejected_terms={trace['rejected_terms']}")
        print(f"hallucination_rate={trace['hallucination_rate']:.3f}")
    else:
        results = retrieve(args.query, top_k=args.top_k)
    print(f"query={args.query}")
    print(f"top_k={args.top_k}")
    for result in results:
        print(
            f"{result['rank']}. {result['id']} | score={result['score']:.4f} | "
            f"{result['title']}"
        )
        print(f"   {result['snippet']}")


if __name__ == "__main__":
    main()
