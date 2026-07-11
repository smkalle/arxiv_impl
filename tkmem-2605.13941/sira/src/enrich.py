"""Offline KB article enrichment for TicketMind/TKMEM."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.index import load_jsonl, tokenize


DEFAULT_OLLAMA_HOST = "http://localhost:11434"
DEFAULT_OLLAMA_MODEL = "qwen2.5:14b"
DEFAULT_TEMPERATURE = 0.3
MAX_TERMS = 12
MIN_TERMS = 8
MIXED_ALNUM_RE = re.compile(r"(?=.*[a-zA-Z])(?=.*\d)^[a-zA-Z0-9_-]+$")


@dataclass
class EnrichmentStats:
    processed: int = 0
    enriched: int = 0
    skipped: int = 0
    failed: int = 0


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_iso_timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def is_already_enriched(article: dict[str, Any]) -> bool:
    enriched_at = parse_iso_timestamp(article.get("enriched_at"))
    last_updated = parse_iso_timestamp(article.get("last_updated"))
    return enriched_at is not None and last_updated is not None and enriched_at >= last_updated


def build_prompt(article: dict[str, Any]) -> str:
    return (
        "Generate 8-12 concise customer-language search terms for this support KB article. "
        "Return only the terms, one per line. Do not repeat words or phrases already present "
        "verbatim in the article.\n\n"
        f"Title: {article.get('title', '')}\n"
        f"Body: {article.get('body', '')}\n"
    )


def call_ollama(article: dict[str, Any], host: str, model: str, temperature: float) -> str:
    host = normalize_host(host)
    response = requests.post(
        f"{host.rstrip('/')}/api/generate",
        json={
            "model": model,
            "prompt": build_prompt(article),
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    return str(payload.get("response", ""))


def normalize_host(host: str) -> str:
    if host.startswith(("http://", "https://")):
        return host
    return f"http://{host}"


def split_raw_terms(raw_response: str) -> list[str]:
    stripped = raw_response.strip()
    if not stripped:
        return []

    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return [str(item) for item in parsed]
        except json.JSONDecodeError:
            pass

    candidates: list[str] = []
    for line in stripped.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if not cleaned:
            continue
        if "," in cleaned:
            candidates.extend(part.strip() for part in cleaned.split(","))
        else:
            candidates.append(cleaned)
    if len(candidates) == 1 and "," in candidates[0]:
        candidates = [part.strip() for part in candidates[0].split(",")]
    return candidates


def normalize_term(term: str) -> str:
    term = term.strip().strip("\"'`")
    term = re.sub(r"\s+", " ", term)
    return term.strip(" .;:")


def should_reject_term(term: str, original_text: str) -> bool:
    if not term:
        return True

    lowered = term.lower()
    if lowered in original_text.lower():
        return True

    words = tokenize(term)
    if not words:
        return True
    if len(words) == 1 and len(words[0]) > 8:
        return True
    return any(MIXED_ALNUM_RE.match(word) for word in words)


def _parse_terms(raw_response: str, original_text: str) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for candidate in split_raw_terms(raw_response):
        term = normalize_term(candidate)
        key = term.lower()
        if key in seen or should_reject_term(term, original_text):
            continue
        seen.add(key)
        terms.append(term)
        if len(terms) >= MAX_TERMS:
            break
    return terms


def heuristic_terms(article: dict[str, Any]) -> list[str]:
    """Deterministic local-dev fallback used when Ollama is unavailable."""
    title = str(article.get("title", "")).lower()
    body = str(article.get("body", "")).lower()
    text = f"{title} {body}"
    mapping = [
        ("login", ["can't sign in", "app shuts down", "login problem", "keeps closing"]),
        ("password", ["reset link missing", "can't get email", "locked out", "email never came"]),
        ("subscription", ["charged again", "renewal problem", "payment won't go through", "billing issue"]),
        ("authenticator", ["code not working", "verification failed", "two step problem", "login code rejected"]),
        ("upload", ["file won't attach", "attachment problem", "upload stuck", "can't send file"]),
        ("locked", ["can't access account", "too many attempts", "sign in blocked", "account unavailable"]),
        ("profile", ["changes disappear", "settings won't save", "profile not updating", "save button failed"]),
        ("notification", ["alerts changed", "preferences disappeared", "wrong alerts", "settings reset"]),
        ("search", ["old results", "can't find update", "results not refreshed", "stale search"]),
        ("invoice", ["receipt won't download", "pdf error", "can't get invoice", "billing document missing"]),
    ]

    selected: list[str] = []
    for marker, terms in mapping:
        if marker in text:
            selected.extend(terms)
    selected.extend(
        [
            "customer report",
            "support request",
            "user issue",
            "troubleshooting help",
            "needs fix",
            "problem report",
            "customer complaint",
        ]
    )
    return _parse_terms("\n".join(selected), text)[:MAX_TERMS]


def build_enriched_body(body: str, terms: list[str]) -> str:
    if not terms:
        return body
    return f"{body}\n\nCustomer language: {'; '.join(terms)}"


def enrich_article(
    article: dict[str, Any],
    host: str,
    model: str,
    temperature: float,
    allow_fallback: bool = True,
) -> tuple[dict[str, Any], bool, bool]:
    if is_already_enriched(article):
        return dict(article), False, False

    original_text = " ".join([str(article.get("title", "")), str(article.get("body", ""))])
    used_fallback = False
    try:
        raw_terms = call_ollama(article, host=host, model=model, temperature=temperature)
        terms = _parse_terms(raw_terms, original_text)
    except requests.RequestException:
        if not allow_fallback:
            raise
        used_fallback = True
        terms = heuristic_terms(article)

    enriched = dict(article)
    now = utc_now_iso()
    enriched.setdefault("last_updated", now)
    enriched["enriched_terms"] = terms
    enriched["enriched_body"] = build_enriched_body(str(article.get("body", "")), terms)
    enriched["enriched_at"] = now
    if used_fallback:
        enriched["enrichment_backend"] = "heuristic-fallback"
    else:
        enriched["enrichment_backend"] = "ollama"
    return enriched, True, used_fallback


def enrich_file(
    input_path: str | Path,
    output_path: str | Path,
    host: str | None = None,
    model: str | None = None,
    temperature: float = DEFAULT_TEMPERATURE,
    allow_fallback: bool = True,
) -> EnrichmentStats:
    host = normalize_host(host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    model = model or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    articles = load_jsonl(input_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    stats = EnrichmentStats()

    with output.open("w", encoding="utf-8") as handle:
        for article in articles:
            stats.processed += 1
            try:
                enriched, changed, _used_fallback = enrich_article(
                    article,
                    host=host,
                    model=model,
                    temperature=temperature,
                    allow_fallback=allow_fallback,
                )
                if changed:
                    stats.enriched += 1
                else:
                    stats.skipped += 1
            except requests.RequestException:
                enriched = dict(article)
                stats.failed += 1
            handle.write(json.dumps(enriched, sort_keys=True) + "\n")
    return stats


def main() -> None:
    parser = argparse.ArgumentParser(description="Enrich KB corpus with customer-language terms.")
    parser.add_argument("--input", required=True, help="Input KB JSONL path")
    parser.add_argument("--output", required=True, help="Output enriched JSONL path")
    parser.add_argument("--host", default=os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    parser.add_argument("--model", default=os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL))
    parser.add_argument("--temperature", type=float, default=DEFAULT_TEMPERATURE)
    parser.add_argument(
        "--no-fallback",
        action="store_true",
        help="Fail articles instead of using deterministic fallback when Ollama is unreachable",
    )
    args = parser.parse_args()

    stats = enrich_file(
        args.input,
        args.output,
        host=normalize_host(args.host),
        model=args.model,
        temperature=args.temperature,
        allow_fallback=not args.no_fallback,
    )
    print(f"processed={stats.processed}")
    print(f"enriched={stats.enriched}")
    print(f"skipped={stats.skipped}")
    print(f"failed={stats.failed}")
    print(f"output={args.output}")
    print(f"ollama_host={normalize_host(args.host)}")
    print(f"ollama_model={args.model}")


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    from src.enrich import main as module_main

    module_main()
