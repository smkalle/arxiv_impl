"""Optional simulated customer.

Off by default. v1 tasks hand the agent a written brief and it works
single-shot, which keeps the reward purely state-based and an episode cheap
enough to run 40 steps on a phone.  The loop is structured so a customer can be
dropped in as one more tool when a task needs clarification behaviour —
tau-bench style — without touching the agent loop itself.

The scripted customer is deterministic, which matters: TaskPilot's solve-rate
estimate is only interpretable if repeated rollouts face the same environment.
An LLM-backed customer is available for realism at the cost of that property.
"""

from __future__ import annotations

import re
from typing import Any

from .backends.base import Backend

_STOPWORDS = {
    "a", "about", "and", "any", "are", "as", "at", "be", "can", "did", "do", "does", "for",
    "have", "how", "i", "in", "is", "it", "many", "me", "much", "my", "of", "on", "or", "please",
    "should", "that", "the", "to", "want", "was", "we", "what", "when", "which", "who", "why",
    "would", "you", "your",
}

EXHAUSTED_REPLY = (
    "I think I've told you everything I know. Use your judgement and the policies."
)

NO_ANSWER_REPLY = (
    "I'm not sure about that one — go with whatever the policy says."
)


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in _STOPWORDS and len(w) > 2}


class ScriptedCustomer:
    """Answers from the task's `customer_facts` by keyword overlap."""

    def __init__(self, facts: dict[str, str], max_turns: int = 6) -> None:
        self.facts = dict(facts)
        self.max_turns = max_turns
        self.turns = 0
        self.transcript: list[tuple[str, str]] = []

    def __call__(self, question: str) -> str:
        if self.turns >= self.max_turns:
            self.transcript.append((question, EXHAUSTED_REPLY))
            return EXHAUSTED_REPLY
        self.turns += 1
        asked = _tokens(question or "")
        best_key, best_score = "", 0
        for key, answer in self.facts.items():
            score = len(asked & (_tokens(key) | _tokens(answer)))
            # A direct mention of the topic key outweighs incidental overlap.
            if key.lower() in (question or "").lower():
                score += 3
            if score > best_score:
                best_key, best_score = key, score
        reply = self.facts[best_key] if best_score > 0 else NO_ANSWER_REPLY
        self.transcript.append((question, reply))
        return reply


class LLMCustomer:
    """A second model plays the customer. Realistic, and no longer deterministic."""

    def __init__(self, backend: Backend, facts: dict[str, str], brief: str, max_turns: int = 6) -> None:
        self.backend = backend
        self.facts = dict(facts)
        self.brief = brief
        self.max_turns = max_turns
        self.turns = 0
        self.transcript: list[tuple[str, str]] = []

    def _system(self) -> str:
        known = "\n".join(f"- {key}: {value}" for key, value in self.facts.items())
        return (
            "You are a car buyer talking to a dealership's self-serve assistant. Answer in "
            "one or two short sentences, the way a person would. Only these facts are true "
            "about you:\n"
            f"{known}\n\n"
            "If you are asked something not covered above, say you are not sure and that "
            "they should use their judgement. Never mention that you are an AI, and never "
            "volunteer information you were not asked for."
        )

    def __call__(self, question: str) -> str:
        if self.turns >= self.max_turns:
            self.transcript.append((question, EXHAUSTED_REPLY))
            return EXHAUSTED_REPLY
        self.turns += 1
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._system()},
            {"role": "user", "content": question or ""},
        ]
        try:
            reply = (self.backend.chat(messages, []).content or "").strip() or NO_ANSWER_REPLY
        except Exception as exc:  # a customer that crashes should not kill the episode
            reply = f"{NO_ANSWER_REPLY} (customer unavailable: {exc})"
        self.transcript.append((question, reply))
        return reply


def make_customer(task: Any, config: Any, backend: Backend | None = None):
    """Return a callable customer, or None when the flag is off."""
    if not getattr(config, "user_sim", False):
        return None
    facts = getattr(task, "customer_facts", {}) or {}
    max_turns = getattr(config, "user_sim_max_turns", 6)
    if backend is not None:
        return LLMCustomer(backend, facts, getattr(task, "brief", ""), max_turns)
    return ScriptedCustomer(facts, max_turns)
