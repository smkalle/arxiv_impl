#!/usr/bin/env python3
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.retrieve import IndexNotLoadedError, load_index, retrieve, sira_retrieve

DEFAULT_INDEX = Path(__file__).parent.parent / "data" / "bm25_index.pkl"
DEFAULT_CORPUS = Path(__file__).parent.parent / "data" / "kb_corpus.jsonl"


def build_index_if_missing(index_path: Path, corpus_path: Path) -> None:
    if not index_path.exists():
        if not corpus_path.exists():
            print(f"Corpus not found at {corpus_path}", file=sys.stderr)
            sys.exit(1)
        from src.index import build_and_save
        print(f"Building index from {corpus_path}...")
        idx = build_and_save(corpus_path, index_path)
        print(f"Index built: {len(idx.articles)} articles\n")


def print_audit_trace(response: dict) -> None:
    print(f"Sketch generated:  {response['sketch_terms_generated']}")
    print(f"Sketch validated:  {response['sketch_terms_validated']}")
    print(f"Sketch rejected:   {response['sketch_terms_rejected']}")
    if response["sketch_terms_generated"]:
        rate = response["hallucination_rate"] * 100
        print(f"Hallucination rate: {rate:.0f}%")
    print()

    if response["fallback_used"]:
        print("⚠️  Fallback to plain BM25 (LLM sketch failed/timeout)")
        print()


def print_results(results: list[dict], sira: bool = False) -> None:
    if not results:
        print("No matching documents found.")
        return

    for i, r in enumerate(results, 1):
        print(f"Rank {i} [score={r['score']}] {r['article_id']} — {r['title']}")
        if sira:
            if r.get("matched_original_terms"):
                print(f"  Matched original: {r['matched_original_terms']}")
            if r.get("matched_enriched_terms"):
                print(f"  Matched enriched: {r['matched_enriched_terms']}")
        print(f"  {r['snippet']}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Query the SIRA BM25 index")
    parser.add_argument("query", help="Query string")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results (default: 5)")
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="Path to BM25 index")
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS, help="Corpus to build index from if missing")
    parser.add_argument("--sira", action="store_true", help="Use full SIRA retrieval with sketch + weighted BM25")
    parser.add_argument("--tau", type=float, default=0.01, help="DF validation upper-bound threshold (default: 0.01)")
    parser.add_argument("--weight", type=float, default=1.5, help="Sketch weight w for weighted BM25 (default: 1.5)")
    args = parser.parse_args()

    build_index_if_missing(args.index, args.corpus)

    try:
        load_index(args.index)
    except FileNotFoundError:
        print(f"Index not found at {args.index}", file=sys.stderr)
        sys.exit(1)

    if args.sira:
        response = sira_retrieve(args.query, top_k=args.top_k, w=args.weight, tau=args.tau)
        print_audit_trace(response)
        print_results(response["results"], sira=True)
    else:
        results = retrieve(args.query, top_k=args.top_k)
        print_results(results, sira=False)


if __name__ == "__main__":
    main()
