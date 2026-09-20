# LeafCX — Leaf + TaskPilot for self-serve account management

An implementation of the inference architecture and curriculum loop from
[arXiv:2609.07925](https://arxiv.org/abs/2609.07925) (FrogNano: Qwen3.5-4B
post-trained with DPPO inside a five-tool harness called **Leaf**, on tasks
selected by an online curriculum called **TaskPilot**), retargeted from software
engineering to a **self-serve customer account surface**.

The flagship task is **shortlisting used cars**. The other five task families
cover the rest of an account-management surface: budget changes, financing
pre-qualification, trade-ins, test-drive scheduling and contact preferences.

Runs on a phone. Termux, no Docker, no GPU required.

---

## Why this port makes sense

The paper's own result is that the **harness** carried most of the pre-RL gain.
Switching the same Qwen3.5-4B base model from R2E-Gym to Leaf moved SWE-bench
Verified from 8.3% to 37.2% before any reinforcement learning; the five RL
iterations then took 43.0% to 61.5%. The harness is the reusable part, and it is
not specific to code.

Account management needs exactly what Leaf provides:

| Leaf / TaskPilot | What it becomes here |
|---|---|
| A git repository | A customer account: JSON files under `account/`, inventory, written policies |
| `read` `write` `edit` `glob` `bash` | The same five, unchanged |
| Reply with no tool call = episode over | Same |
| Hidden F2P + P2P tests, binary reward | Hidden pytest over the final account state, binary reward |
| Gold patch | A reference solution per scenario family |
| TaskPilot: keep tasks with p̂ ≈ 0.5 | Same, over generated account scenarios |

Storing the domain database as local JSON files and grading on final database
state is also how [τ-bench](https://arxiv.org/abs/2406.12045) evaluates
customer-service agents, so the two lineages agree on the mechanism. τ-bench
also reports frontier models under 50% and pass^8 under 25% in retail — there is
plenty of headroom for a 4B model to be measurably bad at, which is what makes a
learnability filter meaningful rather than decorative.

Two domain tools sit on top of Leaf's five — `search_inventory` and
`quote_finance` — and one below them, `validate_account`. They exist because
small models are unreliable at multi-step arithmetic and perfectly capable of
sorting a list they were handed. The task then measures planning and policy
compliance, not mental math.

---

## Install

```bash
cd leaf-taskpilot-2609.07925
pip install pytest          # the only hard dependency: pytest is the grader
python3 -m pytest -q        # 167 tests, no model needed
```

On a phone: `bash scripts/termux_setup.sh` does the above plus prints the
llama.cpp steps.

## Run it without a model

Two offline backends bracket the reward and prove the harness works end to end:

```bash
python3 -m leafcx eval --backend gold --seeds 1-4    # 24/24 — reference solutions
python3 -m leafcx eval --backend noop --seeds 1-4    # 0/24  — stops without acting
```

`gold` is not a lookup table: it runs each scenario's reference solution against
a throwaway copy of the workspace, diffs the account files, and replays the
difference **through real `write` tool calls**. If a `gold` episode does not earn
reward 1, the bug is in the harness.

## Run it with a model

Ollama (the reference tutorial's path):

```bash
ollama pull qwen3.5:4b
python3 -m leafcx doctor
python3 -m leafcx run shortlist_build --seed 1
```

llama.cpp, which is the Termux-friendly path — `--jinja` makes the server use
the model's own chat template, which is what drives tool calling:

```bash
llama-server -m Qwen_Qwen3.5-4B-Q4_K_M.gguf --port 8080 -c 16384 --jinja

export LEAFCX_BACKEND=openai
export LEAFCX_BASE_URL=http://127.0.0.1:8080
python3 -m leafcx run shortlist_build --seed 1
```

Sampling defaults follow the paper's **evaluation** settings (`temperature=0.6`,
`top_p=0.95`), not its training settings (`temperature=1.0, top_p=1.0`, which is
for exploration).

## The commands

```
python3 -m leafcx list                     # the six scenario families
python3 -m leafcx show shortlist_build     # a task's brief and parameters
python3 -m leafcx materialize <family> --gold
python3 -m leafcx run <family> --seed 3
python3 -m leafcx eval --families all --seeds 1-10 --out results.json
python3 -m leafcx validate --seeds 1-10    # are the generated tasks well-posed?
python3 -m leafcx taskpilot --rollouts 4 --iterations 3
python3 -m leafcx doctor                   # can this machine run an episode?
```

---

## The task families

| Family | What the customer wants | What is actually being tested |
|---|---|---|
| `shortlist_build` | "Give me your top 3 and tell me why" | Prose → filters, rank by five-year cost rather than sticker price |
| `profile_update` | "My hours got cut, budget is $X now" | Propagating one change through profile, saved search and shortlist |
| `finance_prequal` | "Can I afford my top pick with $Y down?" | Applying policy honestly, including saying no |
| `trade_in` | "Use my trade-in and rebuild the list" | Composing an external valuation into the budget without editing it |
| `test_drive` | "Cancel that one, book my top pick" | Scheduling under an appointment ceiling, at the right lot |
| `consent_prefs` | "Email me about price drops, stop the texts" | Notification preference ≠ marketing consent |

`consent_prefs` contains the trap that matters commercially. The customer asks
to be emailed about price drops on cars they already chose. A model that reads
"email me" as "opt me into email marketing" flips `consents.marketing_email` and
creates a compliance problem. The preference is the right lever; the consent flag
is not, and a pass-to-pass test fails the episode if it moves.

### Five-year TCO, and why it is the ranking key

The shortlist policy ranks on five-year total cost of ownership — depreciation +
energy + insurance + maintenance — not on asking price. That is the real-world
answer: a new vehicle costs about 72% more than a comparable three-year-old one
but only about $2,478 more over five years of ownership, and used-car APR runs
roughly 2.8 points above new. Sticker price ranks cars wrongly, and a cheap
high-mileage truck routinely loses to a pricier efficient sedan.

`search_inventory` reports `tco_5yr` per vehicle and the policy tells the agent
to copy it. Financing interest is deliberately **excluded** from TCO: two buyers
of the same car with different down payments own an identically costly car.
Interest belongs to the financing quote.

---

## How grading works

1. A scenario builds a task instance from a seed: starting state, customer
   brief, reference solution, generated hidden tests.
2. `workspace/` is wiped and rebuilt. The agent's tools are confined to it.
3. The episode runs until the model replies with no tool call, or the step
   budget is spent.
4. Hidden tests run against the final `account/*.json`.

Reward is **1 if and only if every test passes** — no partial credit, no style
score, no LLM-as-judge. `test_f2p_*` are fail-to-pass; `test_p2p_*` are
pass-to-pass.

Hidden tests live in `hidden_tests/`, a sibling of `workspace/`. The path
sandbox refuses to resolve anything outside the workspace and the `bash`
denylist refuses any command mentioning them, so the agent cannot read them,
edit them, or make them pass by deleting them.

Every generated task is checked for well-posedness before it is used: F2P must
**fail** on the starting state, P2P must **pass** on it, and the reference
solution must turn everything green. `python3 -m leafcx validate` runs that
sweep; the test suite runs it over all six families.

## TaskPilot

```bash
python3 -m leafcx taskpilot --rollouts 4 --iterations 3
```

For each candidate: roll the current policy out N times, estimate p̂, then admit
(0.15 < p̂ < 0.65), refine, or drop. A task the policy never solves is not thrown
away first — it is made *more localising*, because "too hard" is usually
"underspecified". A task solved every time is made behavioural again, and
dropped if it is already as behavioural as its family gets. The final iteration
widens the band to `0 < p̂ ≤ 0.5`, matching the paper's last pass.

Refinement walks a three-rung hint ladder, which is the paper's own worked
example: an underspecified statement solved 0% of the time, a behavioural one
about 50%, a solution-localising one 100% and therefore too easy to keep.

| Hint level | The brief contains |
|---|---|
| 0 | What the customer said, and nothing else |
| 1 | Plus which files to change and which policy page governs them |
| 2 | Plus a step-by-step procedure |

A hint changes the brief only. The task, the reference solution and the hidden
tests are identical across levels — the test suite asserts this.

**One honest caveat.** Without the RL half, the policy does not change between
iterations, so p̂ drifts only through refinement and sampling noise. The
refinement ladder is the part that still does real work locally. Run it to see
which families your model sits on the frontier for; do not read the iteration
index as training progress.

## Metrics the harness collects

The paper reports two behaviours moving under RL, and this harness measures the
same two so a local run can be compared against itself over time:

- **Verification before stopping.** Did the agent call `validate_account` or run
  the visible tests *after* its last change and before ending the episode? The
  paper's checkpoints went from 53.4% to 94.3% on the analogous measure. The
  system prompt asks for it, and `metrics.verified_before_stop` records whether
  it happened.
- **Single-tool-per-turn rate.** The paper's later checkpoints emit one tool
  call per turn about 98% of the time.

Also tracked: step count, tool-call histogram, `edit` failures (a small-model
tell — reaching for `write` when the unique-span `edit` would do), sandbox
blocks, unknown-tool calls, wall time. Every episode writes a JSONL transcript
to `runs/`.

---

## What this is not

**This is not FrogNano.** FrogNano's weights are not released. The paper is a
training report: DPPO on ~1,500 synthetic tasks, 8× B200, 256 concurrent
trajectories, Docker repos, hidden tests, 65k→131k context, 75→150 turns. None
of that runs under Ollama, llama.cpp, or on a phone.

**Do not quote 61.5% from this repo.** That number is FrogNano after five
TaskPilot RL iterations on 1,500 environments. What you can measure here is your
own base model on six generated account-management families.

**The sandbox is best-effort, not a security boundary.** The paper's agent had
an unrestricted shell inside Docker. Termux has no Docker, so confinement here
is path resolution plus a command denylist — enough to stop a confused 4B model
from wandering out of the workspace or editing its own grader, not enough to
stop an adversary. Run untrusted policies in a throwaway container or user
account.

**Training is out of scope.** To actually train, leave this stack: collect
traces here (`reward=1` when the hidden tests pass), then use TRL or Unsloth
GRPO on `Qwen/Qwen3.5-4B`. That is the honest next step, and it is not "FrogNano
in Ollama".

If you only want a local account-management agent and not the training science,
the harness plus "verify before you stop" is most of the win the paper measured
before any RL.

## Layout

```
leafcx/
  config.py          settings, all overridable by environment variable
  policy.py          marketplace rules — one source of truth for tools, pages and tests
  tco.py             five-year cost of ownership + loan arithmetic
  inventory.py       deterministic seeded lot (~300 vehicles, no download)
  constraints.py     hard constraints in one serialisable form
  account.py         account state + policy validation
  sandbox.py         workspace confinement
  tools/             files.py = Leaf's five; domain.py = the three domain tools
  backends/          ollama, openai-compatible, gold, noop, scripted
  scenarios/         the six families, each with a reference solution
  agent.py           the Leaf episode loop and its metrics
  usersim.py         optional simulated customer (off by default)
  grader.py          hidden tests, binary reward, task-validity check
  taskpilot.py       the curriculum
  cli.py             python3 -m leafcx
tests/               the harness's own suite (167 tests, no model needed)
workspace/           generated per episode — gitignored
hidden_tests/        generated, never visible to the agent — gitignored
runs/ tasks/         transcripts and admitted task sets — gitignored
```

## Configuration

| Variable | Default | Notes |
|---|---|---|
| `LEAFCX_BACKEND` | `ollama` | `ollama`, `openai`, `gold`, `noop` |
| `LEAFCX_MODEL` | `qwen3.5:4b` | |
| `LEAFCX_BASE_URL` | backend default | `http://127.0.0.1:8080` for llama-server |
| `LEAFCX_NUM_CTX` | `32768` | drop to 16384 on a phone |
| `LEAFCX_MAX_STEPS` | `40` | the paper's eval averaged ~53 steps/task |
| `LEAFCX_TEMPERATURE` | `0.6` | eval setting, not training |
| `LEAFCX_USER_SIM` | off | enables the `ask_customer` tool |
| `LEAFCX_WORKSPACE` | `./workspace` | |
| `LEAFCX_HIDDEN_TESTS` | `./hidden_tests` | must stay outside the workspace |

## The simulated customer

Off by default: v1 tasks hand the agent a written brief and it works
single-shot, which keeps the reward purely state-based and an episode cheap
enough to run on a phone. `--user-sim` adds an `ask_customer` tool backed by a
deterministic scripted customer that answers from the task's known facts.
Determinism matters here — TaskPilot's p̂ is only interpretable if repeated
rollouts face the same environment. An `LLMCustomer` is available in
`usersim.py` for realism at the cost of that property.
