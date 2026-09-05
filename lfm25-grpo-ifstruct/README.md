# LFM2.5-350M + GRPO → schema-compliant structured output

A hands-on Colab notebook for the recipe in
[*Fine-tuning a 350M Model for Better Structured Outputs in 100 GRPO Steps*](https://huggingface.co/blog/grpo-with-trl-ifstruct)
(Monigatti, Burtenshaw & Paniego — Hugging Face, 3 Sep 2026). Reported result:
[IFStruct](https://github.com/Liquid4All/ifstruct) **22.6% (452/2000) → 29.7% (594/2000)**
after ~500 rows and 100 GRPO steps — JSON drove it (18.0% → 31.9%), YAML was flat
(27.2% → 27.5%) because the recipe trains JSON only.

**Notebook:** [`lfm25_350m_grpo_structured_outputs.ipynb`](lfm25_350m_grpo_structured_outputs.ipynb)
(61 cells) — open in Colab, *Runtime → T4 GPU*, run top to bottom with `SMOKE_TEST=True` first.

## Design: official training, official scoring

- **The training half is Liquid's.** Data source, filters, augmentation, LoRA targets, all
  three reward functions and every hyperparameter are taken verbatim from
  [`Liquid4All/cookbook`](https://github.com/Liquid4All/cookbook/blob/main/finetuning/notebooks/grpo_with_trl_ifstruct.ipynb).
- **The evaluation half calls Liquid's scorer.** Rather than re-implement the six IFStruct
  checks, the notebook `pip install`s the [`ifstruct`](https://github.com/Liquid4All/ifstruct)
  package and calls `validate_response()` — the function behind the published numbers.

That split is deliberate: training optimises a `jsonschema` proxy over the Nemotron
`schema_str`, while the benchmark is measured with the stricter official validator. The
notebook says so explicitly, because it means a rising reward curve does *not* by itself
guarantee a rising IFStruct score.

| § | Step |
|---|---|
| 2–3 | Pinned installs; load the official validator and frozen 2,000-row test set |
| 4 | Nemotron data: clean (length, `$ref`, Draft 7) and augment 40/20/40 |
| 5 | Load LFM2.5-350M, assert the LoRA targets exist, attach the adapter |
| 6 | Baseline on real IFStruct under a fixed evaluation contract |
| 7 | The three official rewards + adversarial unit tests |
| 8 | GRPO config, preflight, training, 4-panel diagnostics |
| 9–10 | Re-measure, paired sign test, error-category deltas, run card |
| 11–13 | Official GGUF/`llama-server` eval path, serving pattern, troubleshooting |
| A | A YAML-capable training-set generator (Run B — *not* the published reproduction) |

## Getting the facts right

Five things are wrong in most circulating summaries; each was checked against primary
sources:

- **Training data is `nvidia/Nemotron-RL-instruction_following-structured_outputs`**,
  1,000 rows filtered to ~500 — not IFStruct, and not synthetic.
- **`out_proj`, not `o_proj`** — LFM2's attention output projection. PEFT silently ignores
  target names that match nothing, so a copied list leaves blocks untrained. The notebook
  enumerates `nn.Linear` modules and asserts every target exists.
- **bf16 does not exist on a T4** (Turing, SM 7.5); compute capability is detected.
- **IFStruct's `json_schema` root is always `{"type": "array"}`**, describing the
  *unwrapped* list. Validating it per item fails every row.
- **No 4-bit quantization** — 350M in fp16 is ~0.7 GB, and quantising slows generation,
  which is GRPO's bottleneck.

## Verified before publication

Run on CPU against the real benchmark (training cells need a GPU):

- All 38 code cells compile; every CPU-runnable cell executes clean in notebook order.
- `reference_answer()` passes the official validator on **2,000/2,000** real test rows —
  the harness is proven before any score is trusted.
- Reward unit tests pass, including the hack probes: `{}` → 0.0, backtick spam → 0.0,
  wrong-form → 0.2 (above unparseable, below correct).
- Data prep exercised against a mock Nemotron-shaped dataset: filters fire and the
  augmentation lands at **41/20/39**.
- Appendix generator: **500/500** rows satisfiable, **zero** prompt overlap with the test set.

## Expectations

The in-notebook subset score is a **regression test**, not a publishable number — fewer
rows and a smaller token budget than the official harness. The before/after delta under
an identical contract (same rows, greedy decoding, single user message, no system prompt)
is the result, and §9 reports an exact paired sign test because a 150-row sample carries
roughly ±4pp of standard error.

For a number comparable to 22.6% / 29.7%, use the GGUF → `llama-server` → `ifstruct-eval`
path in §11, and score the base model through the identical stack.
