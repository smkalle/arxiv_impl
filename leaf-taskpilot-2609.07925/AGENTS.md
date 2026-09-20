# AGENTS.md — leaf-taskpilot-2609.07925 (LeafCX)

Leaf + TaskPilot (arXiv:2609.07925) retargeted from SWE tasks to a self-serve
used-car account-management surface. Read `README.md` first for what it is, then
`SPEC.md` for why each piece is shaped the way it is.

## Commands

Run everything **from this directory**, with `python3` (there is no `python` on
PATH anywhere in this repo).

```bash
pip install pytest                 # the only hard dependency
python3 -m pytest -q               # the harness's own suite; no model needed
python3 -m leafcx eval --backend gold --seeds 1-4    # must be 24/24
python3 -m leafcx eval --backend noop --seeds 1-4    # must be 0/24
python3 -m leafcx validate --seeds 1-10              # generated tasks well-posed?
```

There is no linter or formatter configured. Match the surrounding style:
`from __future__ import annotations`, dataclasses over dicts for structured
values, module docstrings that say *why*.

## Invariants — break these and the numbers stop meaning anything

1. **`leafcx/policy.py` is the single source of truth.** The same constants feed
   the domain tools, the markdown pages written into the workspace, and the
   hidden tests. Never hard-code a rule in a scenario or a test. If a number
   changes, the policy page regenerates with it — `test_domain_math.py` asserts
   every APR, term and ceiling appears in the page that governs it.
2. **Hidden tests never touch the workspace.** `hidden_tests/` is a sibling of
   `workspace/`, not a child. `sandbox.resolve_in_workspace` refuses to resolve
   it and `sandbox.check_command` refuses any command naming it.
3. **Every generated task must be well-posed**: F2P fails on the starting state,
   P2P passes on it, and the reference solution earns reward 1.
   `grader.validate_task` checks all three; `tests/test_grader.py` runs it over
   all six families.
4. **Determinism.** A `(family, seed)` pair must always produce byte-identical
   briefs, params and hidden tests. The inventory generator is seeded; nothing
   in a scenario may read the clock or the global RNG.
5. **A hint level changes the brief only.** `params`, the reference solution and
   the hidden tests are identical across hint levels 0, 1 and 2. TaskPilot's
   refinement depends on this.
6. **No gold answer may be ambiguous.** Where a scenario ranks vehicles, the
   builder must reject draws with a TCO tie at the cut line — see
   `base.has_strict_separation`. An ambiguous task punishes the policy for a
   problem we created.
7. **Reward stays binary.** All tests pass, or reward is 0. No partial credit, no
   style score, no LLM judge.

## Adding a scenario family

1. Subclass `scenarios.base.Scenario` with `family`, `summary`, `build`,
   `materialize` and `solve`.
2. `build(seed, hint_level)` must retry its draw until the instance is
   well-posed, and raise rather than emit a degenerate task. Look at
   `trade_in._draw_task` for why: a budget-only constraint made that family
   vacuous, because the TCO-cheapest cars are also among the cheapest to buy, so
   raising the ceiling never changed the optimum. A model-year floor fixed it.
3. Write hidden tests through `base.hidden_test_module`, naming them
   `test_f2p_*` and `test_p2p_*`. At least one of each.
4. Register it in `scenarios/__init__.py`.
5. You get the `gold` backend for free — it derives its plan by running your
   `solve()` against a throwaway copy of the workspace and diffing.
6. `python3 -m leafcx validate --families <yours> --seeds 1-10` must be clean.

## Adding a tool

Add the callable and its JSON schema together in `leafcx/tools/`, and register
both. Keep domain tools thin: they surface facts (inventory rows, loan
arithmetic) and never decide anything. The agent must still choose, rank,
justify and write the account files itself — that is what is being measured.

## Generated paths

`workspace/`, `hidden_tests/`, `runs/` and `tasks/` are all generated and
gitignored at the repo root. Never commit them. The test suite redirects all
four to `tmp_path` via `tests/conftest.py`, so running the suite never touches
the checkout.

## Honesty rules for this subproject

- Do not report SWE-bench-style numbers from this harness. It measures a base
  model on six generated account-management families, nothing more.
- The sandbox is best-effort — path resolution plus a command denylist, because
  Termux has no Docker. Say so wherever it comes up; do not describe it as
  isolation.
- FrogNano's weights are not released. This is the inference architecture and
  the curriculum loop, not the policy.
