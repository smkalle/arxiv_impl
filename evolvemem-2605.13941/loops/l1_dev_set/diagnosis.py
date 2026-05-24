"""L1 diagnosis prompt and LLM call."""
from __future__ import annotations

import json
from typing import Any

from loops.llm import LLMProvider, extract_json

L1_DIAGNOSIS_SYSTEM_PROMPT = """\
You are an AutoResearch agent optimizing a dev set sampling strategy for an \
IT support ticket → KB article resolution system.

Your task: propose ONE change to DevSetConfig that will increase the quality \
of the fitness signal — making the dev set harder, more representative, or more diverse.

DevSetConfig fields you may change:
  min_csat (int 1-5): minimum CSAT score for including a resolved ticket
  n_train (int 50-200): number of training pairs
  vocab_gap_ratio (float 0.0-0.5): fraction of pairs with low lexical overlap (harder)
  augmentation_strategy (str): "none" | "paraphrase" | "synonym"
  random_seed (int): any integer for reproducibility

Current config: {config_json}
Current F1 gain (round3_f1 - round0_f1): {f1_gain:.4f}
F1 history: {history}
Stagnating: {stagnating}

If stagnating=True, propose a change you have not tried before in this run.
Output JSON only — no explanation."""


def run_l1_diagnosis(
    llm: LLMProvider,
    config: Any,
    f1_gain: float,
    history: list[float],
    stagnating: bool,
) -> str:
    user_prompt = (
        f"config: {json.dumps(config.to_dict())}\n"
        f"f1_gain: {f1_gain:.4f}\n"
        f"history: {history}\n"
        f"stagnating: {stagnating}"
    )
    system = L1_DIAGNOSIS_SYSTEM_PROMPT.format(
        config_json=json.dumps(config.to_dict()),
        f1_gain=f1_gain,
        history=history,
        stagnating=stagnating,
    )
    return llm.complete(system=system, user=user_prompt, temperature=0.4)
