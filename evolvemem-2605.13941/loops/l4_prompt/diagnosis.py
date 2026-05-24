"""L4 meta-loop diagnosis — proposes improvements to the L3 diagnosis prompt."""
from __future__ import annotations

from loops.llm import LLMProvider

L4_DIAGNOSIS_SYSTEM_PROMPT = """\
You are a meta-AutoResearch agent. Your task is to improve the diagnosis prompt \
used by the L3 retrieval loop to propose better RetrievalConfig patches.

The L3 diagnosis prompt is what instructs the LLM to analyse retrieval failures and \
suggest a config patch. A better prompt → better patches → higher F1 gain per round.

Current L3 diagnosis prompt:
---
{current_prompt}
---

Current mean F1 delta per L3 round: {mean_delta:.4f}
F1 delta history: {history}
Stagnating: {stagnating}

Improvements to consider:
  - Add concrete few-shot examples of high-quality diagnosis outputs
  - Strengthen the stagnation instruction: when stagnating, try a dimension never tried before
  - Add a domain glossary: crash↔segfault, login↔authenticate, billing↔payment
  - Add a constraint: never propose the same dimension twice in one run
  - Clarify vocabulary-gap detection instructions for IT support language

Return the full improved L3 diagnosis prompt text. Do NOT return JSON. \
Return only the prompt text, ready to use as a system prompt."""


def run_l4_diagnosis(
    llm: LLMProvider,
    current_prompt: str,
    mean_delta: float,
    history: list[float],
    stagnating: bool,
) -> str:
    system = L4_DIAGNOSIS_SYSTEM_PROMPT.format(
        current_prompt=current_prompt,
        mean_delta=mean_delta,
        history=history,
        stagnating=stagnating,
    )
    return llm.complete(
        system=system,
        user=f"mean_f1_delta={mean_delta:.4f}. Produce the improved L3 diagnosis prompt.",
        temperature=0.6,
    )
