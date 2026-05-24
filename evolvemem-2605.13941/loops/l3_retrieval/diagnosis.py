"""
L3 diagnosis prompt and LLM call.

DIAGNOSIS_SYSTEM_PROMPT is a module-level constant so that:
  1. L3Loop reads it at call time (allowing L4 to inject a new version)
  2. L4's editor writes the evolved version here and to data/evolved/diagnosis_prompt.txt
"""
from __future__ import annotations

import json
from typing import Any

from loops.llm import LLMProvider

DIAGNOSIS_SYSTEM_PROMPT = """\
You are an AutoResearch agent optimizing retrieval configuration for an IT support \
ticket → KB article resolution system.

Your task: propose ONE patch to RetrievalConfig that will increase F1@5 on the dev set.

Configuration dimensions you may set:
  top_k (int 1-20): number of results to retrieve
  bm25_weight (float 0.1-3.0): weight for BM25 keyword retrieval view
  semantic_weight (float 0.0-2.0): weight for semantic embedding view
  symbolic_weight (float 0.0-1.0): weight for tag/symbolic view
  tau (float 0.001-0.5): document-frequency filter threshold
  rerank (bool): apply cross-encoder reranking pass
  query_expansion (bool): expand query with related terms before retrieval
  entity_swap (bool): bridge vocabulary gaps using domain synonym mapping
  entity_swap_domain (str): "it_support" for IT support ticket synonyms
  recency_weight (float 0.0-0.5): boost recently-created articles
  recency_window_days (int 30-365): look-back window for recency boost
  answer_verification (bool): post-retrieve answer verification pass

You may also propose entirely NEW dimension keys — they will be stored and applied.

Domain context: tickets use customer language (crash, broken, not working);
KB articles use engineering language (segfault, exception, invalidation).
Bridging this vocabulary gap is the primary driver of F1 improvement.

Current RetrievalConfig: {config_json}
Current F1@5: {f1:.4f}
F1 history across rounds: {history}
Stagnating: {stagnating}

If stagnating=True, propose a dimension you have NOT proposed before in this run.
Output JSON only — no explanation."""


def run_l3_diagnosis(
    llm: LLMProvider,
    config: Any,
    f1: float,
    history: list[float],
    stagnating: bool,
    prompt_override: str | None = None,
) -> str:
    system = (prompt_override or DIAGNOSIS_SYSTEM_PROMPT).format(
        config_json=json.dumps(config.to_dict()),
        f1=f1,
        history=history,
        stagnating=stagnating,
    )
    return llm.complete(
        system=system,
        user=f"F1@5={f1:.4f}. Propose a RetrievalConfig patch to improve it.",
        temperature=0.5,
    )
