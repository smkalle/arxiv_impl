import math


def dcg_at_k(ranked_ids: list[str], gains: dict[str, float], k: int) -> float:
    dcg = 0.0
    for rank, article_id in enumerate(ranked_ids[:k], start=1):
        gain = gains.get(article_id, 0.0)
        if gain <= 0:
            continue
        dcg += gain / math.log2(rank + 1)
    return dcg


def idcg_at_k(gains: dict[str, float], k: int) -> float:
    ideal = sorted((g for g in gains.values() if g > 0), reverse=True)
    if not ideal:
        return 0.0
    dcg = 0.0
    for rank, gain in enumerate(ideal[:k], start=1):
        dcg += gain / math.log2(rank + 1)
    return dcg


def ndcg_at_k(ranked_ids: list[str], gains: dict[str, float], k: int) -> float:
    ideal = idcg_at_k(gains, k)
    if ideal == 0:
        return 0.0
    return dcg_at_k(ranked_ids, gains, k) / ideal


def recall_at_k(ranked_ids: list[str], relevant_ids: set[str], k: int) -> float:
    if not relevant_ids:
        return 0.0
    hits = len(set(ranked_ids[:k]).intersection(relevant_ids))
    return hits / len(relevant_ids)


def reciprocal_rank(ranked_ids: list[str], relevant_ids: set[str]) -> float:
    for rank, article_id in enumerate(ranked_ids, start=1):
        if article_id in relevant_ids:
            return 1.0 / rank
    return 0.0


def _normalize_gains(qrel: dict) -> dict[str, float]:
    grades = qrel.get("relevance_grades")
    if grades:
        return {str(article_id): float(score) for article_id, score in grades.items() if float(score) > 0}
    relevant_ids = qrel.get("relevant_article_ids", [])
    return {str(article_id): 1.0 for article_id in relevant_ids}


def compute_metrics(results: dict[str, list[str]], qrels: dict[str, dict]) -> dict[str, float]:
    ndcg5_vals = []
    ndcg10_vals = []
    recall5_vals = []
    recall10_vals = []
    mrr_vals = []

    for ticket_id, qrel in qrels.items():
        gains = _normalize_gains(qrel)
        if not gains:
            continue
        ranked = results.get(ticket_id, [])
        relevant = set(gains.keys())

        ndcg5_vals.append(ndcg_at_k(ranked, gains, 5))
        ndcg10_vals.append(ndcg_at_k(ranked, gains, 10))
        recall5_vals.append(recall_at_k(ranked, relevant, 5))
        recall10_vals.append(recall_at_k(ranked, relevant, 10))
        mrr_vals.append(reciprocal_rank(ranked, relevant))

    if not ndcg5_vals:
        raise ValueError("No valid qrels with relevant documents were provided")

    n = len(ndcg5_vals)
    return {
        "ndcg@5": round(sum(ndcg5_vals) / n, 4),
        "ndcg@10": round(sum(ndcg10_vals) / n, 4),
        "recall@5": round(sum(recall5_vals) / n, 4),
        "recall@10": round(sum(recall10_vals) / n, 4),
        "mrr": round(sum(mrr_vals) / n, 4),
        "num_queries": n,
    }
