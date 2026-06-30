# AGENTS.md — rgqm (EpochForge Lite)

## Status

**Spec-only. No implementation code yet.** Build horizon ~5–6 weeks (solo). The canonical PRD is `rqgm-gemini-spec.html` (v0.2); `rqgm-visual-explainer.html` is the paper explainer. Read the spec HTML before writing any code — this file is a navigation aid, not a substitute.

Implements a **minimal prototype of the Red Queen Gödel Machine** (arXiv:2606.26294): co-evolving task agent + evaluator, epoch-gated utility evolution, ε-best-belief evaluator promotion, selective erasure. Everything not on that critical path is cut.

---

## Stack and hard constraints (will break correctness/faithfulness if violated)

- **One model only: `gemini-3.5-flash`**, for every LLM call (meta-agent, coder, reviewer). No other model is in scope. `MODEL` is a constant at the top of `llm.py`.
- **Do NOT set `temperature`, `top_p`, or `top_k`** for Gemini 3.5 Flash — Google recommends defaults only. Control behavior via `thinking_level` instead.
- **`thinking_level`: `"medium"` for the meta-agent** (needs reasoning depth for code edits); **`"low"` for coder + reviewer** calls (latency-sensitive).
- **Reviewer system prompt (~1,200 tokens, identical across all 80 calls) is cached** via the Gemini caching endpoint. Cached input = $0.15/1M vs $1.50/1M uncached. Cache TTL = 600s (covers one full run).
- **Reviewer's ground-truth anchor = the same HumanEval test suite** used to score the coder — *not* a separate dataset like CRAVE. A challenger reviewer wins promotion if it better predicts which coder solutions pass tests, measured on a 50-sample held-out (task, solution) split built at run start.
- **Four flat Python files, no package, no ABCs, no modules.** All state is passed explicitly; all state lives in one `archive.json`.
- **Workspace model:** each archive node's "codebase" is just two Python strings — `coder_fn` and `reviewer_fn` — stored directly in the node dict. The meta-agent returns a JSON object with updated versions of either/both. **No filesystem, no git, no diff application.**
- **`archive.json` is written atomically after every step** (temp-file + rename). Three top-level arrays: `nodes`, `utility_records`, `epoch_events`. References are by string ID (no FK constraints).
- **Sandbox = `subprocess` + `tempdir`.** No Docker.
- **Exactly one epoch boundary**, at checkpoint step 30 (total budget B=80). `mode="rqgm"` enables it; `mode="hgm_h"` disables it (the baseline).
- **HGM-H baseline = the same code with a frozen reviewer** (`mode="hgm_h"`). It is not a separate codebase.
- **Blended token metric = input + 5×output** (the paper's metric). Cost basis: $1.50/1M input, $9.00/1M output.
- **LRU cache on reviewer outputs** (`solution_hash`, `reviewer_fn_hash` → same binary score, no API call). Selective erasure re-runs scoring on the cached text, **not** a new Gemini call.
- **API budget guardrail: < $20 total** across all runs (baseline + RQGM + 3 variance runs). Per-run target $3–5 uncached, $2.50–4 with reviewer caching. Spike cost with `thinking_level="low"` on eval calls before committing to task pool size.

---

## Planned file layout (spec §4 — not yet created)

The spec names the package dir `epochforge-lite/`; the subproject folder is `rgqm/`. Confirm the code location with the user before scaffolding.

```
archive.py     # Archive tree + Thompson sampling over CMP + ε-best-belief; owns selective_erase() + recompute_clade()
search.py      # Main loop: UCB-Air gate + epoch manager + 3-level sampler (node→role→task, least-eval first)
agents.py      # MetaAgent (code diffs) / CoderAgent (HumanEval solution) / ReviewerAgent (0/1 score); all call llm.call()
llm.py         # google-genai SDK wrapper; context cache; blended token/cost counters; LRU reviewer cache
plot.py        # results.json → matplotlib chart; RQGM vs HGM-H; vertical dashed line at epoch boundary
tasks/humaneval_20.json   # 20 stratified HumanEval tasks: {task_id, prompt, test_code, difficulty}
archive.json   # runtime state (gitignored)
```

---

## Epoch protocol essentials (spec §6)

The single boundary at step 30 is the whole point of the prototype — implement it correctly.

- Steps 0–29: normal search. All reviewer records tagged `epoch=0`; coder test records tagged `is_verifiable=true`.
- Step 30: score all reviewer nodes on the held-out 50-sample set → ε-best-belief contest → promote winner (ties keep incumbent) or retain. **If promoted:** delete every `utility_records` row with `role="reviewer"` AND `epoch=0`, increment epoch to 1, recompute clade aggregates, log to `epoch_events`. `reviewer_output_cache` lets erased records be re-scored without extra API calls.
- Steps 31–80: continue under the new/same reviewer; new reviewer records tagged `epoch=1`.

**Erasure invariant (CI-enforced):** after every `selective_erase()` call, assert
`len([r for r in archive["utility_records"] if r["role"]=="reviewer" and r["epoch"]==0]) == 0`.
This runs on every commit and after every simulated boundary in the integration test.

**Erasable vs. permanent:** only `is_verifiable=false` (reviewer) records are erasable. Coder (`is_verifiable=true`) records are never deleted.

---

## Two-phase build plan (spec §7) — Phase 2 is purely additive

**Phase 1 — HGM-H baseline (weeks 1–3):** everything except epoch machinery. Deliverables: HumanEval loader + subprocess test runner; archive dict + atomic JSON persistence; ε-best-belief via `scipy.stats` Beta quantile; Thompson sampling over CMP; UCB-Air expand/evaluate gate; 3-level sampler; Coder/Reviewer/Meta agents; `llm.py`; HGM-H run; `results.json` + `plot.py`.

**Phase 2 — co-evolution (weeks 4–6):** held-out 50-sample GT set; `epoch` + `is_verifiable` fields; `selective_erase()` + `recompute_clade_aggregates()`; `run_epoch_boundary()` (atomic JSON write); erasure-invariant pytest; full RQGM run (B=80, checkpoint=30); comparison plot; patch-attribution logging (`%` of meta-agent edits touching `reviewer_fn`); 3 variance runs.

Phase 2 needs no rewrites — the boundary check is a single `if mode == "rqgm" and step == CHECKPOINT` guard in `search.py`.

---

## Exit criteria (spec §8)

- **P0 — token efficiency:** RQGM reaches the same held-out pass rate as HGM-H using ≥10% fewer blended tokens.
- **P0 — erasure invariant:** 0 stale reviewer records after a boundary (pytest-enforced).
- **P1 — evaluator improvement:** promoted reviewer's GT accuracy ≥2pp above the epoch-0 incumbent on the 50-sample held-out set.
- **P1 — budget:** <$20 total Gemini API spend across all runs.

**Not a success criterion:** reproducing the paper's exact 71.7% pass rate or 1.72× token savings. The prototype uses 20 tasks (vs. full Polyglot), a different model, and a smaller budget. The bar is **directional correctness of the mechanism**, not numerical replication.

---

## Out of scope (do not build)

Docker isolation; SQLite/SQLAlchemy/any DB; Streamlit or any web dashboard; CRAVE or any external evaluator GT dataset; adversarial pool / adversarial epochs; specialist-vs-generalist distinction; multiple evaluator slots (M > 1); polyglot/multi-language benchmark; more than one epoch boundary; parallel/distributed search; any model other than `gemini-3.5-flash`; production API/auth/multi-user.

---

## Open questions (resolve before build, spec §9)

1. Can Gemini 3.5 Flash write functional Python patches reliably? Spike: prompt it to modify a simple function 20×, measure rate of syntactically valid + meaningfully different outputs. If <50%, consider Sonnet for meta-agent calls only.
2. Reviewer = fixed prompted LLM (meta-agent evolves only the prompt string) vs. full co-evolved code function? Prompt-as-evaluator is cheaper/stabler but question its faithfulness to the paper.
3. Are 20 HumanEval tasks enough signal? With B=80 over ~25 nodes, each node gets ~3 evals — ε-best-belief is very wide. Consider 40 tasks or B=160 (both double cost).
4. Seed node init: minimal coder (returns empty) + minimal reviewer (always 1), or a weak-but-passable Gemini-generated seed (one extra API call)?
5. No-challenger-at-step-30 fallback: if the archive is coder-dominant, the boundary fires as `no_challenger` and the run continues as HGM-H. Decide whether to force reviewer lineage seeding or prompt the meta-agent to also evolve `reviewer_fn`.
