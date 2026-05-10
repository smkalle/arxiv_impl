import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from tqdm import tqdm

from src.index import read_jsonl

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")


ENRICHMENT_PROMPT = """You are an expert support knowledge-base indexer.
Given the KB article below, generate 8–12 NEW discriminative search terms
that a customer would use when experiencing the problem described, but that
DO NOT appear in the article text.

Focus on:
- Plain customer language equivalents of technical jargon
- Common error messages a user might see (colloquial forms)
- Related symptoms that imply this root cause
- Abbreviations, typos, and alternate product names customers actually use

Output ONLY a comma-separated list. No explanations. No numbering.

KB Article:
{article_text}
"""


def _default_llm_call(prompt: str, model: str = DEFAULT_MODEL) -> str:
    """Call Ollama chat API. Override this in tests."""
    import ollama

    client = ollama.Client(host=OLLAMA_HOST)
    response = client.chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        options={"temperature": 0.3, "num_predict": 200},
    )
    return response["message"]["content"]


def _is_low_quality(term: str) -> bool:
    t = term.lower()
    if len(t) <= 1:
        return True
    if any(c.isdigit() for c in t) and any(c.isalpha() for c in t):
        return True
    if " " not in t and len(t) > 8:
        return True
    return False


def _parse_terms(raw: str, original_text: str, telemetry: dict | None = None) -> list[str]:
    original_lower = original_text.lower()
    parts = raw.split(",")
    terms = []
    dropped = []
    for part in parts:
        term = part.strip()
        if not term:
            continue
        t = term.lower()
        if t in original_lower:
            dropped.append({"term": term, "reason": "appears in original text"})
            continue
        if _is_low_quality(term):
            is_mixed = any(c.isdigit() for c in t) and any(c.isalpha() for c in t)
            dropped.append({"term": term, "reason": "mixed alphanumeric" if is_mixed else "too long / concatenated"})
            continue
        terms.append(term)
    if telemetry is not None:
        telemetry["raw_term_count"] = len(parts)
        telemetry["filtered_term_count"] = len(terms)
        telemetry["dropped_terms"] = dropped
    return terms


def enrich_article(
    article: dict,
    llm_call: Callable[[str, str], str] = _default_llm_call,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
    telemetry: dict | None = None,
) -> dict:
    """Enrich a single article with LLM-generated customer-language terms."""
    article_id = article["article_id"]
    original_body = article.get("body", "")
    title = article.get("title", "")
    full_text = title + "\n" + original_body
    t0 = time.time()

    for attempt in range(1, max_retries + 1):
        try:
            raw = llm_call(ENRICHMENT_PROMPT.format(article_text=full_text), model)
            terms = _parse_terms(raw, full_text, telemetry=telemetry)
            enriched_body = original_body + " " + " ".join(terms)
            result = dict(article)
            result.update({
                "original_body": original_body,
                "enriched_body": enriched_body,
                "enriched_terms": terms,
                "enriched_at": datetime.now(timezone.utc).isoformat(),
                "model_used": model,
            })
            if telemetry is not None:
                telemetry["duration_sec"] = round(time.time() - t0, 2)
                telemetry["retries"] = attempt
                telemetry["success"] = True
                result["telemetry"] = telemetry
            return result
        except Exception as exc:
            logger.warning("Enrichment failed for %s (attempt %d/%d): %s", article_id, attempt, max_retries, exc)
            if attempt < max_retries:
                time.sleep(1)
            else:
                if telemetry is not None:
                    telemetry["duration_sec"] = round(time.time() - t0, 2)
                    telemetry["retries"] = attempt
                    telemetry["success"] = False
                    telemetry["error"] = str(exc)
                raise


def enrich_corpus(
    input_path: str | Path,
    output_path: str | Path,
    llm_call: Callable[[str, str], str] = _default_llm_call,
    model: str = DEFAULT_MODEL,
    max_retries: int = 3,
) -> dict:
    """Batch-enrich a corpus JSONL. Returns summary stats."""
    articles = read_jsonl(input_path)

    enriched = []
    skipped = 0
    failed = 0

    for art in tqdm(articles, desc="Enriching articles"):
        if art.get("enriched_at") and art.get("last_updated"):
            enriched_at = datetime.fromisoformat(art["enriched_at"].replace("Z", "+00:00"))
            last_updated = datetime.fromisoformat(art["last_updated"].replace("Z", "+00:00"))
            if enriched_at.tzinfo is None:
                enriched_at = enriched_at.replace(tzinfo=timezone.utc)
            if last_updated.tzinfo is None:
                last_updated = last_updated.replace(tzinfo=timezone.utc)
            if enriched_at >= last_updated:
                enriched.append(art)
                skipped += 1
                continue

        try:
            new_art = enrich_article(art, llm_call=llm_call, model=model, max_retries=max_retries)
            enriched.append(new_art)
        except Exception:
            logger.exception("Skipping article %s after all retries failed", art.get("article_id"))
            enriched.append(art)
            failed += 1

    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        for art in enriched:
            f.write(json.dumps(art, ensure_ascii=False) + "\n")

    sample_terms = enriched[0].get("enriched_terms", []) if enriched else []
    return {
        "total": len(articles),
        "enriched": len(articles) - skipped - failed,
        "skipped": skipped,
        "failed": failed,
        "sample_terms": sample_terms,
    }


def main():
    parser = argparse.ArgumentParser(description="Offline enrichment batch job for SIRA")
    parser.add_argument("--input", default="data/kb_corpus.jsonl", help="Input corpus path")
    parser.add_argument("--output", default="data/enriched_corpus.jsonl", help="Output enriched corpus path")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Ollama model tag")
    args = parser.parse_args()

    stats = enrich_corpus(args.input, args.output, model=args.model)
    print(f"Enriched {stats['enriched']}/{stats['total']} articles")
    print(f"Skipped {stats['skipped']} (already current), failed {stats['failed']}")
    if stats["sample_terms"]:
        print(f"Sample terms: {stats['sample_terms'][:5]}")


if __name__ == "__main__":
    main()
