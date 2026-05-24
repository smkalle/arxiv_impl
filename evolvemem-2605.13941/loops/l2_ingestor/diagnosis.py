"""L2 diagnosis prompt and LLM call."""
from __future__ import annotations

import json
from typing import Any

from loops.llm import LLMProvider

L2_DIAGNOSIS_SYSTEM_PROMPT = """\
You are an AutoResearch agent optimizing KB article chunking for an IT support \
ticket → KB article resolution system.

Your task: propose ONE change to IngestorConfig that will increase the synthesis \
ratio (chunks merged per article) or raise the F1 ceiling.

IngestorConfig fields you may change:
  chunk_strategy (str): "paragraph" | "sliding_window" | "sentence"
  max_chunk_tokens (int 128-1024): maximum tokens per chunk
  min_chunk_chars (int 10-100): skip chunks shorter than this
  chunk_overlap (int 0-200): overlap chars between sliding-window chunks
  add_product_area_entity (bool): add product_area as entity tag

Constraint: chunk_overlap must be less than max_chunk_tokens * 4.

Current config: {config_json}
synthesis_ratio: {synthesis_ratio:.4f}  (higher = better compression)
F1 ceiling: {f1_ceiling:.4f}
fitness (ratio × ceiling): {fitness:.4f}
Fitness history: {history}
Stagnating: {stagnating}

If stagnating=True, try a different chunk_strategy.
Output JSON only — no explanation."""


def run_l2_diagnosis(
    llm: LLMProvider,
    config: Any,
    synthesis_ratio: float,
    f1_ceiling: float,
    fitness: float,
    history: list[float],
    stagnating: bool,
) -> str:
    system = L2_DIAGNOSIS_SYSTEM_PROMPT.format(
        config_json=json.dumps(config.to_dict()),
        synthesis_ratio=synthesis_ratio,
        f1_ceiling=f1_ceiling,
        fitness=fitness,
        history=history,
        stagnating=stagnating,
    )
    return llm.complete(
        system=system,
        user=f"Propose a patch to IngestorConfig. fitness={fitness:.4f}",
        temperature=0.4,
    )
