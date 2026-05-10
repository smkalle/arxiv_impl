from collections import Counter


def validate_sketch_terms(
    terms: list[str],
    df_counter: Counter,
    N: int,
    tau: float = 0.01,
) -> dict:
    """Validate sketch terms against document-frequency statistics.

    Returns a dict with:
        validated: list of terms that pass the filter
        rejected: list of terms that fail the filter
        rejected_reasons: list of dicts with term and reason
    """
    validated = []
    rejected = []
    rejected_reasons = []
    threshold = tau * N

    for term in terms:
        t = term.lower()
        df = df_counter.get(t, 0)
        if df == 0:
            rejected.append(t)
            rejected_reasons.append({"term": t, "reason": "df=0"})
        elif df > threshold:
            rejected.append(t)
            rejected_reasons.append({"term": t, "reason": "too_common"})
        else:
            validated.append(t)

    return {
        "validated": validated,
        "rejected": rejected,
        "rejected_reasons": rejected_reasons,
    }
