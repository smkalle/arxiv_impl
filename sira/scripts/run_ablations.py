#!/usr/bin/env python3
import argparse
import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.eval import compute_metrics
from src.index import build_and_save
from src.retrieve import load_index, retrieve, sira_retrieve


def load_test_set(path: Path) -> tuple[dict[str, str], dict[str, dict]]:
    queries = {}
    qrels = {}
    with open(path) as f:
        for line_no, line in enumerate(f, start=1):
            raw = line.strip()
            if not raw:
                continue
            row = json.loads(raw)
            ticket_id = row.get("ticket_id")
            ticket_text = row.get("ticket_text")
            relevant_article_ids = row.get("relevant_article_ids")
            if not ticket_id or not ticket_text or not isinstance(relevant_article_ids, list):
                raise ValueError(f"Invalid row at line {line_no}: required fields missing or malformed")
            queries[ticket_id] = ticket_text
            qrels[ticket_id] = {
                "relevant_article_ids": relevant_article_ids,
                "relevance_grades": row.get("relevance_grades", {}),
            }
    if not queries:
        raise ValueError("Test set is empty")
    return queries, qrels


def _run_plain(queries: dict[str, str], top_k: int) -> tuple[dict[str, list[str]], dict[str, float]]:
    ranked = {}
    for ticket_id, text in queries.items():
        results = retrieve(text, top_k=top_k)
        ranked[ticket_id] = [r["article_id"] for r in results]
    return ranked, {"fallback_rate": 0.0, "hallucination_rate": 0.0}


def _run_sira(queries: dict[str, str], top_k: int, weight: float, tau: float) -> tuple[dict[str, list[str]], dict[str, float]]:
    ranked = {}
    fallback_count = 0
    hallucination_values = []
    for ticket_id, text in queries.items():
        response = sira_retrieve(text, top_k=top_k, w=weight, tau=tau)
        ranked[ticket_id] = [r["article_id"] for r in response.get("results", [])]
        if response.get("fallback_used"):
            fallback_count += 1
        if response.get("sketch_terms_generated"):
            hallucination_values.append(float(response.get("hallucination_rate", 0.0)))

    fallback_rate = fallback_count / len(queries)
    avg_hallucination = sum(hallucination_values) / len(hallucination_values) if hallucination_values else 0.0
    return ranked, {
        "fallback_rate": round(fallback_rate, 4),
        "hallucination_rate": round(avg_hallucination, 4),
    }


def percent_delta(new: float, base: float) -> float:
    if base == 0:
        return 0.0
    return ((new - base) / base) * 100


def print_table(rows: list[dict]) -> None:
    print("+----------------------------+--------+---------+----------+-----------+-------+")
    print("| Experiment                 | nDCG@5 | nDCG@10 | Recall@5 | Recall@10 | MRR   |")
    print("+----------------------------+--------+---------+----------+-----------+-------+")
    for row in rows:
        print(
            "| {exp:<26} | {n5:>6} | {n10:>7} | {r5:>8} | {r10:>9} | {mrr:>5} |".format(
                exp=row["name"][:26],
                n5=f"{row['metrics']['ndcg@5']:.3f}",
                n10=f"{row['metrics']['ndcg@10']:.3f}",
                r5=f"{row['metrics']['recall@5']:.3f}",
                r10=f"{row['metrics']['recall@10']:.3f}",
                mrr=f"{row['metrics']['mrr']:.3f}",
            )
        )
    print("+----------------------------+--------+---------+----------+-----------+-------+")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run SIRA ablation experiments")
    parser.add_argument("--test-set", type=Path, default=Path("tests/annotated_test_set.jsonl"))
    parser.add_argument("--plain-corpus", type=Path, default=Path("data/kb_corpus.jsonl"))
    parser.add_argument("--enriched-corpus", type=Path, default=Path("data/enriched_corpus.jsonl"))
    parser.add_argument("--top-k", type=int, default=10)
    parser.add_argument("--tau", type=float, default=0.01)
    args = parser.parse_args()

    queries, qrels = load_test_set(args.test_set)

    with tempfile.TemporaryDirectory(prefix="sira_ablation_") as tmp_dir:
        tmp = Path(tmp_dir)
        plain_index_path = tmp / "plain_index.pkl"
        enriched_index_path = tmp / "enriched_index.pkl"

        build_and_save(args.plain_corpus, plain_index_path)
        build_and_save(args.enriched_corpus, enriched_index_path)

        rows = []

        load_index(plain_index_path)
        ranked, diag = _run_plain(queries, top_k=args.top_k)
        rows.append({"name": "1. Baseline BM25", "metrics": compute_metrics(ranked, qrels), "diag": diag})

        load_index(enriched_index_path)
        ranked, diag = _run_plain(queries, top_k=args.top_k)
        rows.append({"name": "2. Enrichment only", "metrics": compute_metrics(ranked, qrels), "diag": diag})

        load_index(plain_index_path)
        ranked, diag = _run_sira(queries, top_k=args.top_k, weight=1.5, tau=args.tau)
        rows.append({"name": "3. Sketch only", "metrics": compute_metrics(ranked, qrels), "diag": diag})

        load_index(enriched_index_path)
        ranked, diag = _run_sira(queries, top_k=args.top_k, weight=1.5, tau=args.tau)
        rows.append({"name": "4. Full SIRA (w=1.5)", "metrics": compute_metrics(ranked, qrels), "diag": diag})

        for weight in (1.0, 1.5, 2.0):
            load_index(enriched_index_path)
            ranked, diag = _run_sira(queries, top_k=args.top_k, weight=weight, tau=args.tau)
            rows.append({"name": f"5. SIRA w={weight}", "metrics": compute_metrics(ranked, qrels), "diag": diag})

    print_table(rows)

    baseline = rows[0]["metrics"]
    full_sira = rows[3]["metrics"]
    ndcg10_gain = percent_delta(full_sira["ndcg@10"], baseline["ndcg@10"])
    recall5_gain = percent_delta(full_sira["recall@5"], baseline["recall@5"])

    pass_ndcg = ndcg10_gain >= 10.0
    pass_recall = recall5_gain >= 15.0
    verdict = "PASS" if pass_ndcg and pass_recall else "FAIL"

    print(
        f"Go/No-Go: {verdict} "
        f"(nDCG@10 {ndcg10_gain:+.1f}%, Recall@5 {recall5_gain:+.1f}% vs baseline)"
    )
    print()
    print("Sketch diagnostics:")
    for row in rows:
        if row["diag"]["fallback_rate"] == 0.0 and row["diag"]["hallucination_rate"] == 0.0 and "SIRA" not in row["name"] and "Sketch" not in row["name"]:
            continue
        print(
            f"- {row['name']}: fallback_rate={row['diag']['fallback_rate']:.3f}, "
            f"hallucination_rate={row['diag']['hallucination_rate']:.3f}"
        )


if __name__ == "__main__":
    main()
