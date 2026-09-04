# LFM2.5-350M + GRPO → schema-compliant structured output

A hands-on notebook that reconstructs the recipe from
[*Fine-tuning a 350M Model for Better Structured Outputs in 100 GRPO Steps*](https://huggingface.co/blog/grpo-with-trl-ifstruct)
(Leonie Monigatti, Ben Burtenshaw, Sergio Paniego — Hugging Face, 3 Sep 2026):
take `LiquidAI/LFM2.5-350M`, apply Group Relative Policy Optimization with TRL over
~500 prompts and 100 steps, and lift [IFStruct](https://github.com/Liquid4All/ifstruct)
schema compliance. The published run reports **22.6% → 29.7%**; a later, longer Liquid
run on the same checkpoint reached **44.9%**.

**Notebook:** [`lfm25_350m_grpo_structured_outputs.ipynb`](lfm25_350m_grpo_structured_outputs.ipynb)
(54 cells) — open in Colab, set *Runtime → T4 GPU*, run top to bottom.

## What it does

| § | Step |
|---|---|
| 3 | Installs Liquid's **official IFStruct validator** and loads the frozen 2,000-row test set |
| 4 | Loads LFM2.5-350M, discovers its real LoRA target names, attaches an adapter |
| 5 | Baseline pass rate on a fixed sample of the real test set |
| 6 | Generates a 500-row IFStruct-style **training** set (the public split is test-only) |
| 7 | Seven staged reward functions built on the official validator |
| 8 | 100 GRPO steps with TRL |
| 9 | Re-measure, paired significance test, per-axis and per-error deltas |
| 10–11 | Inference wrapper with validate-and-repair; troubleshooting |

The load-bearing design choice is that **reward and metric are the same code**:
every reward is derived from one call to `ifstruct.validator.validate_response`, so
there is no scoring drift between what training optimises and what the benchmark reports.

## Verified before publication

Run on CPU against the real benchmark (training cells require a GPU):

- All 32 code cells compile; CPU cells execute clean in notebook order.
- The notebook's `reference_answer()` constructor passes the official validator on
  **2,000/2,000** real test rows — confirming the spec semantics it teaches
  (notably: `json_schema` is always `{"type": "array"}` describing the *unwrapped*
  list, and a YAML request rejects flow-style/JSON-shaped output).
- The generated training set is **600/600 satisfiable** with **zero prompt overlap**
  against the test set.
- The reward ladder was adversarially tested against 10 mutations; both classic reward
  hacks (empty container, schema echoed back as data) score near the floor.
- The documented `ArrowInvalid` failure mode is reproduced, confirming why
  `json_schema` / `top_level_count` must be stored as JSON strings.

## Corrections to the commonly-copied snippet

The notebook flags several details that are wrong or fragile in circulating versions
of this recipe:

- **`out_proj`, not `o_proj`** — LFM2's attention output projection. PEFT silently
  ignores target names that match nothing, so a copied list leaves blocks untrained.
  The notebook enumerates `nn.Linear` modules instead of hard-coding names.
- **bf16 does not exist on a T4** (Turing, SM 7.5). The notebook detects compute
  capability and selects fp16, including for the 4-bit compute dtype.
- **`json_schema` models the unwrapped array**, not a wrapper object.
- **4-bit is unnecessary at 350M** (~0.7 GB in fp16) and costs generation speed, which
  is GRPO's bottleneck; it is an opt-in flag, off by default.
- **Evaluation matches the official harness**: one user message, no system prompt,
  greedy decoding. Adding a helpful system prompt inflates the score and breaks
  comparability with the published baseline.

## Expectations

Absolute numbers will not match the published 22.6% / 29.7%: the official harness scores
all 2,000 rows with an 8,000-token cap, while the notebook scores a subset under a T4-sized
cap. **The before/after delta, measured under identical settings, is the result** — and
with a 150-row sample its standard error is ±3–4 points, which is why §9 runs a paired
sign test rather than trusting the raw difference.
