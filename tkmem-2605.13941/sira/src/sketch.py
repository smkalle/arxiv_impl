"""Online ticket sketch generation."""

from __future__ import annotations

import json
import os
import re
from typing import Any

import requests

from src.enrich import DEFAULT_OLLAMA_HOST, DEFAULT_OLLAMA_MODEL, normalize_host
from src.index import tokenize


DEFAULT_SKETCH_TEMPERATURE = 0.1
DEFAULT_SKETCH_TIMEOUT = 0.5


def parse_sketch_terms(raw_response: str) -> list[str]:
    stripped = raw_response.strip()
    if not stripped:
        return []
    if stripped.startswith("["):
        try:
            parsed = json.loads(stripped)
            if isinstance(parsed, list):
                return _clean_terms(str(item) for item in parsed)
        except json.JSONDecodeError:
            pass
    pieces: list[str] = []
    for line in stripped.splitlines():
        cleaned = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if not cleaned:
            continue
        pieces.extend(part.strip() for part in cleaned.split(","))
    return _clean_terms(pieces)


def _clean_terms(pieces) -> list[str]:
    terms: list[str] = []
    seen: set[str] = set()
    for piece in pieces:
        normalized = " ".join(tokenize(str(piece)))
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        terms.append(normalized)
        if len(terms) >= 12:
            break
    return terms


def heuristic_sketch(ticket_text: str) -> list[str]:
    lowered = ticket_text.lower()
    mapping = [
        ("crash", ["login", "session", "token", "authentication", "mobile"]),
        ("login", ["authentication", "session", "token", "lockout", "sign"]),
        ("password", ["password", "reset", "email", "delivery", "account"]),
        ("subscription", ["subscription", "renewal", "billing", "payment", "idempotency"]),
        ("renew", ["subscription", "renewal", "billing", "payment", "processor"]),
        ("invoice", ["invoice", "pdf", "archive", "download", "rendering"]),
        ("search", ["search", "index", "synchronization", "records", "reindex"]),
    ]
    terms: list[str] = []
    for marker, values in mapping:
        if marker in lowered:
            terms.extend(values)
    terms.extend(tokenize(ticket_text))
    return _clean_terms(terms)[:12]


def generate_sketch(
    ticket_text: str,
    host: str | None = None,
    model: str | None = None,
    temperature: float = DEFAULT_SKETCH_TEMPERATURE,
    allow_fallback: bool = True,
    timeout: float = DEFAULT_SKETCH_TIMEOUT,
) -> list[str]:
    host = normalize_host(host or os.getenv("OLLAMA_HOST", DEFAULT_OLLAMA_HOST))
    model = model or os.getenv("OLLAMA_MODEL", DEFAULT_OLLAMA_MODEL)
    prompt = (
        "Generate 8-12 concise KB jargon search terms for this support ticket. "
        "Return only terms, one per line.\n\n"
        f"Ticket: {ticket_text}\n"
    )
    try:
        response = requests.post(
            f"{host.rstrip('/')}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {"temperature": temperature},
            },
            timeout=timeout,
        )
        response.raise_for_status()
        terms = parse_sketch_terms(str(response.json().get("response", "")))
    except requests.RequestException:
        if not allow_fallback:
            raise
        terms = heuristic_sketch(ticket_text)
    return terms
