# SPEC — LeafCX

Design record: what was ported from arXiv:2609.07925, what was changed, and why.

## 1. What the paper contains, and what is reproducible

FrogNano is Qwen3.5-4B post-trained with DPPO on ~1,500 synthetic SWE tasks
inside a five-tool harness (Leaf), with an online curriculum (TaskPilot).
Training: 8× B200, 256 concurrent trajectories, Docker-backed repositories,
hidden tests, group size 8 with zero-advantage groups discarded, a success-gated
log length penalty on winning traces only, 0.5 partial credit for truncated
successes, no KL, no entropy bonus, 200 updates × 32 groups × 8 rollouts per
iteration, context 65k then 131k, 75 then 150 turns.

None of that runs locally. What does:

| Component | Status here |
|---|---|
| Leaf harness | Reproduced |
| Termination on a tool-free reply | Reproduced |
| Hidden F2P/P2P tests, binary reward | Reproduced |
| Gold patch per task | Reproduced (reference solution per family) |
| TaskPilot p̂ estimation and admission band | Reproduced |
| TaskPilot refinement ladder | Reproduced |
| DPPO / any weight update | **Out of scope** |
| FrogNano checkpoint | **Not released** |

The port is justified by the paper's own decomposition: the harness change
(R2E-Gym → Leaf) moved the same base model from 8.3% to 37.2% on SWE-bench
Verified *before* RL; RL then moved 43.0% → 61.5%. The larger single jump is the
part that transfers to a new domain.

## 2. Domain choice

**Self-serve account management, used-car marketplace.** Chosen because it has
the property a binary state-based reward needs: a computable correct answer.

Prior art for the reward mechanism is τ-bench (arXiv:2406.12045), which
evaluates customer-service agents by storing the domain database as local JSON
files and comparing final database state against an annotated goal state. That
is structurally the same as Leaf's "keep the agent's edits, discard edits to
test files, run hidden F2P + P2P". Both lineages therefore agree, and the
account files here are simultaneously the database and the graded artifact.

τ-bench also reports frontier function-calling agents under 50% and pass^8 under
25% in retail. A 4B model has room to be measurably bad, which is what makes a
learnability filter meaningful instead of decorative.

## 3. Decisions taken with the human before implementation

| Fork | Decision | Why |
|---|---|---|
| Tool surface | Leaf's five **plus** three domain tools | Keeps the harness recognisable; the extra three remove arithmetic the 4B model would fail for uninteresting reasons |
| Scope | Full account lifecycle, shortlist as flagship | The brief was "account mgmt use cases, used cars as an example" |
| Runtime | Ollama-first, llama.cpp documented and supported | Mirrors the reference tutorial; the OpenAI-compatible backend is the Termux path |
| Simulated customer | Single-shot now, user-sim behind a flag | Keeps the reward state-based and episodes phone-sized; the loop is structured so a customer drops in as one more tool |

Data source was not put to the human: a seeded deterministic generator is the
only option that is offline, reproducible and phone-sized. ~300 vehicles, no
download.

## 4. Tools

Leaf's five are unchanged: `read`, `write`, `edit`, `glob`, `bash`. `edit`
requires its `old` span to match exactly once — the paper's detail worth copying
verbatim, because small models otherwise reach for `write` and flatten a file
they meant to touch in one place. `metrics.edit_failures` tracks how often that
bites.

The three domain tools:

- `search_inventory` — filters the lot and attaches `tco_5yr` per vehicle.
- `quote_finance` — prices a loan for one VIN against the financing policy,
  reading credit band, income and any trade-in from the account.
- `validate_account` — checks the account against the written policies.

They surface facts and never decide. The agent still chooses, ranks, justifies
and writes. `validate_account` exists specifically as a *verification lever*:
the paper's clearest behavioural finding is that successful agents close with
executable verification, and its checkpoints moved from 53.4% to 94.3% on that
measure. Giving the model something cheap to verify with, and asking for it in
the system prompt, is how that behaviour is made available locally.

## 5. Reward

Binary. Reward 1 iff every `test_f2p_*` and `test_p2p_*` in the task's generated
hidden-test module passes. Grading runs pytest as a subprocess with
`--junit-xml` and parses the XML, which is stable across pytest versions.

Task validity is checked, not assumed. `grader.validate_task` materialises the
task, grades the untouched starting state (F2P must fail, P2P must pass), applies
the reference solution, and grades again (everything must pass). A generated task
that misses any of those three is broken and teaches a policy nothing.

## 6. Cost model

Five-year TCO = depreciation + energy + insurance + maintenance. Financing
interest is excluded by design: two buyers of the same vehicle with different
down payments own an identically costly car, so interest belongs to the
financing quote, not to ownership cost.

Parameters are anchored on 2026 market data: used-car APR near 9.7% for prime
and roughly 2.8pp above new; a new vehicle costing about 72% more than a
comparable three-year-old one while being only about $2,478 more expensive over
five years. The point of ranking on TCO rather than price is that price ranks
cars wrongly, and the shortlist policy page says so in as many words.

The agent is never asked to compute TCO. `search_inventory` reports it and the
policy says to copy it. This is deliberate: a 4B model is unreliable at
multi-step arithmetic and perfectly capable of sorting a list it was given, so
the task measures planning and policy compliance rather than mental math.

## 7. Scenario families

Six, each a task *family* from which `build(seed, hint_level)` draws one
reproducible instance.

| Family | Tests |
|---|---|
| `shortlist_build` | Prose → filters; ranking by cost of ownership; well-formed output |
| `profile_update` | Propagating one change across profile, saved search and shortlist without disturbing what still qualifies |
| `finance_prequal` | Applying policy honestly; about half of instances cannot be pre-qualified |
| `trade_in` | Composing an external valuation into the budget without editing the appraisal |
| `test_drive` | Scheduling under an appointment ceiling, at the vehicle's own lot |
| `consent_prefs` | Distinguishing a notification preference from a marketing consent |

Two build-time constraints that took iteration:

- **Strict separation.** Where a family ranks vehicles, the builder rejects any
  draw where the size-th best candidate ties on TCO with the next one. Otherwise
  the "correct" shortlist depends on a VIN tiebreak the agent cannot infer, and a
  binary reward punishes the policy for our ambiguity.
- **Non-vacuous drawing.** `trade_in` initially generated tasks where applying
  the trade changed nothing, because with a budget-only constraint the
  TCO-cheapest cars are also among the cheapest to buy, so raising the ceiling
  never moves the optimum. A model-year floor puts the efficient vehicles above
  the cash budget and makes the trade worth applying.

## 8. TaskPilot

`classify(p̂, band, hint_level)` → keep / make_easier / make_harder / drop.
Iterations before the last use `0.15 < p̂ < 0.65`; the final iteration widens to
`0 < p̂ ≤ 0.5`, matching the paper's last pass.

"Too hard" is refined *before* it is dropped, because too hard is usually
underspecified. The hint ladder reproduces the paper's worked example:
underspecified → 0%, behavioural → ~50%, solution-localising → 100% and
therefore too easy to keep. A hint level changes only the brief; params, the
reference solution and the hidden tests are identical across levels, and the
test suite asserts it.

Each seed is refined at most once per iteration pass, or a task stuck at p̂=0
would walk the whole ladder inside a single pass and stop being an estimate of
anything.

**Limitation, stated plainly.** Without the RL half the policy does not change
between iterations, so p̂ drifts only through refinement and sampling noise. The
iteration index is not training progress. What the loop is genuinely useful for
locally is finding which families your model currently sits on the frontier for.

## 9. Sandbox

Best-effort, and described as such everywhere. The paper's agent had an
unrestricted shell inside Docker; Termux has no Docker. What exists here is
path resolution (absolute paths, `..` segments and symlinks pointing out are all
refused) plus a command denylist covering the hidden tests, parent traversal,
recursive deletes outside the workspace, network tools, package installation and
privilege escalation. Enough to stop a confused 4B model; not a boundary against
an adversary.

## 10. Backends

| Name | Transport | Purpose |
|---|---|---|
| `ollama` | `POST /api/chat`, stdlib urllib | Default; matches the reference tutorial |
| `openai` | `POST /v1/chat/completions` | llama.cpp `llama-server --jinja`, vLLM, remote APIs — the Termux path |
| `gold` | none | Replays the reference solution through real tool calls; reward ceiling |
| `noop` | none | Stops immediately; reward floor |
| `scripted` | none | Fixed turn list, for the harness's own tests |

No third-party HTTP dependency. `urllib` is enough, and it keeps `pip install`
on a phone down to pytest.

`gold` derives its plan rather than hard-coding it: it copies the workspace,
runs the scenario's `solve()` on the copy, diffs the account files, and emits
the differences as `write` calls, one tool call per turn. New scenarios get a
gold agent for free, and a failing `gold` episode localises the bug to the
harness.

## 11. Metrics

Per episode: step count, tool-call histogram, `edit` failures, sandbox blocks,
unknown-tool calls, single-tool-turn rate, whether the agent verified after its
last change and before stopping, wall time. Transcripts are JSONL under `runs/`.

The first and last of those mirror what the paper reports moving under RL
(~98% single-tool turns; 53.4% → 94.3% verification), so a local run can be
compared against itself over time even though the absolute numbers are not
comparable to the paper's.

## 12. Deliberately out of scope

- Any weight update. Collect traces here, then use TRL or Unsloth GRPO on
  `Qwen/Qwen3.5-4B` — a different stack, honestly named.
- Real inventory feeds, real credit decisions, real PII. Every customer,
  vehicle and appraisal in this repo is generated.
- Multi-customer or multi-agent orchestration. One account, one episode.
