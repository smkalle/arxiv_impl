import logging
import os
from typing import Callable

logger = logging.getLogger(__name__)

DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

SKETCH_PROMPT = """You are a support resolution expert.
Given the customer ticket below, generate an "expected resolution vocabulary sketch":
8–12 key technical terms, product component names, or KB jargon that would
likely appear in the article that resolves this ticket, but are ABSENT from
the ticket text itself.

Do NOT guess the actual answer. Generate vocabulary bridges only.
Output ONLY a comma-separated list. No explanations.

Customer Ticket:
{ticket_text}
"""


def _default_llm_call(prompt: str, model: str = DEFAULT_MODEL) -> str:
    import ollama
    import threading

    client = ollama.Client(host=OLLAMA_HOST)
    result = {}
    error = {}

    def _call():
        try:
            result["content"] = client.chat(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.1, "num_predict": 250},
            )
        except Exception as exc:
            error["exc"] = exc

    t = threading.Thread(target=_call, daemon=True)
    t.start()
    t.join(timeout=12.0)
    if t.is_alive():
        raise TimeoutError(f"LLM call timed out after 12s for model {model}")
    if error:
        raise error["exc"]
    return result["content"]["message"]["content"]


def generate_sketch(
    ticket_text: str,
    model: str = DEFAULT_MODEL,
    llm_call: Callable[[str, str], str] = _default_llm_call,
) -> list[str]:
    """Generate resolution vocabulary sketch for a ticket.

    Returns a list of lowercase, stripped terms. On any failure returns [].
    """
    try:
        raw = llm_call(SKETCH_PROMPT.format(ticket_text=ticket_text), model)
    except Exception as exc:
        logger.warning("Sketch generation failed: %s", exc)
        return []

    terms = []
    for part in raw.split(","):
        term = part.strip().lower()
        if term:
            terms.append(term)

    # deduplicate while preserving order
    seen = set()
    unique_terms = []
    for t in terms:
        if t not in seen:
            seen.add(t)
            unique_terms.append(t)
    return unique_terms
