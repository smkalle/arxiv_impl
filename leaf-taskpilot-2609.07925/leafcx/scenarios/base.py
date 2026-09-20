"""Scenario scaffolding: how a task instance is built, materialised and graded.

A scenario family is the account-management analogue of a repository in the
paper.  One *instance* is the analogue of a SWE task: a starting state, a
customer brief that plays the role of the issue text, a gold solution that plays
the role of the gold patch, and hidden tests the agent never sees.
"""

from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .. import inventory as inventory_mod
from .. import policy

#: Extra brief sections appended per hint level.  This ladder is what TaskPilot
#: walks when it refines a task: level 0 states the outcome, level 1 points at
#: the files, level 2 spells out the procedure.  The paper's own example runs
#: the same way — underspecified gives 0% solve, behavioural ~50%, and
#: solution-localising 100%, at which point the task is too easy and is dropped.
HINT_LEVELS = (0, 1, 2)


@dataclass
class TaskInstance:
    """One concrete, reproducible task."""

    task_id: str
    family: str
    seed: int
    hint_level: int
    brief: str
    params: dict[str, Any]
    hidden_test_source: str
    #: Facts the simulated customer knows, keyed by topic. Only consulted when
    #: the `ask_customer` tool is enabled.
    customer_facts: dict[str, str] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "family": self.family,
            "seed": self.seed,
            "hint_level": self.hint_level,
            "params": self.params,
            "brief": self.brief,
        }


class Scenario:
    """Base class for a scenario family."""

    family: str = "unnamed"
    #: One-line description used by the CLI listing.
    summary: str = ""

    def build(self, seed: int, hint_level: int = 0) -> TaskInstance:
        raise NotImplementedError

    def materialize(self, task: TaskInstance, root: Path) -> None:
        raise NotImplementedError

    def solve(self, task: TaskInstance, root: Path) -> None:
        """Apply the gold solution. Used by the `gold` backend and task validation."""
        raise NotImplementedError


# --------------------------------------------------------------------------
# Shared materialisation
# --------------------------------------------------------------------------

VISIBLE_TEST_SOURCE = '''"""Visible checks. The agent can and should run these:

    python3 -m pytest -q tests/

They confirm the account files are well-formed. They do NOT confirm the
customer's request was satisfied -- the graded tests are elsewhere and are not
visible from here.
"""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ACCOUNT = ROOT / "account"


def _load(name):
    path = ACCOUNT / name
    if not path.exists():
        return None
    return json.loads(path.read_text())


def test_account_files_are_valid_json():
    for path in sorted(ACCOUNT.glob("*.json")):
        json.loads(path.read_text())


def test_profile_has_required_fields():
    profile = _load("profile.json")
    assert profile is not None, "account/profile.json is missing"
    for field in ("customer_id", "budget_max", "annual_miles"):
        assert field in profile, f"profile is missing {field}"


def test_shortlist_shape():
    shortlist = _load("shortlist.json")
    if shortlist is None:
        return
    assert isinstance(shortlist, dict) and isinstance(shortlist.get("entries"), list)
    ranks = [e["rank"] for e in shortlist["entries"] if isinstance(e, dict) and "rank" in e]
    assert sorted(ranks) == list(range(1, len(shortlist["entries"]) + 1)), (
        f"ranks must be 1..n with no gaps; got {sorted(ranks)}"
    )
'''


def default_profile(seed: int, **overrides: Any) -> dict[str, Any]:
    profile: dict[str, Any] = {
        "customer_id": f"CUST-{seed % 100000:05d}",
        "name": "Dana Whitfield",
        "email": "dana.whitfield@example.com",
        "phone": "+1-555-0142",
        "ssn_last4": "4417",
        "drivers_license": "D2291874",
        "household_size": 2,
        "budget_max": 22000,
        "cash_down": 3000,
        "annual_miles": policy.DEFAULT_ANNUAL_MILES,
        "commute_miles_daily": 34,
        "credit_band": "good",
        "gross_monthly_income": 5400,
        "home_charging": False,
        "preferred_locations": ["Fremont", "San Jose"],
        "consents": {
            "marketing_email": False,
            "marketing_sms": False,
            "data_sharing_partners": False,
        },
        "notifications": {
            "price_drop_email": False,
            "price_drop_sms": True,
            "new_match_email": True,
            "appointment_reminder_sms": True,
        },
    }
    profile.update(overrides)
    return profile


def empty_account_files() -> dict[str, Any]:
    return {
        "shortlist.json": {"updated_by": "system", "entries": []},
        "saved_searches.json": {"searches": []},
        "finance.json": {},
        "trade_in.json": {},
        "appointments.json": {"appointments": []},
        "audit_log.json": {"events": [{"ts": "2026-09-01T09:00:00", "event": "account_created"}]},
    }


def materialize_common(
    root: Path,
    task: TaskInstance,
    inventory: list[dict[str, Any]],
    profile: dict[str, Any],
    account_overrides: dict[str, Any] | None = None,
) -> None:
    """Write a fresh workspace: inventory, account, policies, visible tests, brief."""
    if root.exists():
        shutil.rmtree(root)
    (root / "account").mkdir(parents=True)
    (root / "inventory").mkdir(parents=True)
    (root / "policies").mkdir(parents=True)
    (root / "tests").mkdir(parents=True)

    (root / "inventory" / "vehicles.json").write_text(json.dumps(inventory, indent=2) + "\n")

    files = empty_account_files()
    files["profile.json"] = profile
    files.update(account_overrides or {})
    for name, payload in files.items():
        (root / "account" / name).write_text(json.dumps(payload, indent=2) + "\n")

    for name, body in policy.policy_pages().items():
        (root / "policies" / name).write_text(body)

    (root / "tests" / "test_visible.py").write_text(VISIBLE_TEST_SOURCE)
    (root / "CUSTOMER_REQUEST.md").write_text(task.brief)


def build_inventory(seed: int, count: int = 300) -> list[dict[str, Any]]:
    return inventory_mod.generate_inventory(seed=seed, count=count)


# --------------------------------------------------------------------------
# Hidden tests
# --------------------------------------------------------------------------

_HIDDEN_HEADER = '''"""Generated hidden tests -- NOT visible to the agent.

`test_f2p_*` are fail-to-pass: they must fail on the starting state.
`test_p2p_*` are pass-to-pass: they must pass before and after.
Reward is binary and requires every test in this file to pass.
"""

import json
import os
from pathlib import Path

from leafcx import account, policy, tco

PARAMS = json.loads(r"""{params_json}""")
ROOT = Path(os.environ["LEAFCX_WORKSPACE"]).resolve()


def load(name, default=None):
    path = ROOT / name
    if not path.exists():
        return default
    return json.loads(path.read_text())


def shortlist_entries():
    data = load("account/shortlist.json", {{"entries": []}}) or {{"entries": []}}
    entries = [e for e in data.get("entries", []) if isinstance(e, dict)]
    entries.sort(key=lambda e: e.get("rank", 10**6))
    return entries


def shortlist_vins():
    return [e.get("vin") for e in shortlist_entries()]


def test_p2p_account_passes_policy_validation():
    problems = [p for p in account.validate(ROOT) if not p.startswith("note:")]
    assert problems == [], "policy validation failed:\\n" + "\\n".join(problems)


def test_p2p_sensitive_fields_not_leaked():
    profile = load("account/profile.json", {{}}) or {{}}
    for field in policy.SENSITIVE_PROFILE_FIELDS:
        value = profile.get(field)
        if not value:
            continue
        for path in sorted((ROOT / "account").glob("*.json")):
            if path.name == "profile.json":
                continue
            assert str(value) not in path.read_text(), f"{{field}} leaked into {{path.name}}"
'''


def hidden_test_module(params: dict[str, Any], body: str) -> str:
    """Render a hidden-test module with `params` baked in as a JSON literal."""
    params_json = json.dumps(params, indent=2)
    if '"""' in params_json:
        raise ValueError("scenario params must not contain a triple quote")
    return _HIDDEN_HEADER.format(params_json=params_json) + "\n\n" + body.strip() + "\n"


# --------------------------------------------------------------------------
# Brief assembly
# --------------------------------------------------------------------------


def assemble_brief(
    headline: str,
    customer_words: str,
    hint_level: int,
    localising: str = "",
    procedural: str = "",
) -> str:
    """Build CUSTOMER_REQUEST.md at the requested hint level."""
    parts = [f"# {headline}", "", "## What the customer said", "", customer_words.strip(), ""]
    if hint_level >= 1 and localising.strip():
        parts += ["## Where to work", "", localising.strip(), ""]
    if hint_level >= 2 and procedural.strip():
        parts += ["## Suggested procedure", "", procedural.strip(), ""]
    parts += [
        "## How you are graded",
        "",
        "The final state of `account/*.json` is what counts. Read `policies/` before you "
        "change anything, use `validate_account` when you think you are done, and run "
        "`python3 -m pytest -q tests/`. Reply with no tool call to finish.",
        "",
    ]
    return "\n".join(parts)


def rank_key(vehicle: dict[str, Any], annual_miles: int) -> tuple[Any, ...]:
    """Total order used by the shortlist policy: TCO, then price, then mileage, then VIN."""
    from .. import tco as tco_mod

    return (
        tco_mod.tco_5yr(vehicle, annual_miles=annual_miles),
        vehicle["price"],
        vehicle["mileage"],
        vehicle["vin"],
    )


def pick_shortlist(
    vehicles: list[dict[str, Any]],
    annual_miles: int,
    size: int,
    predicate: Callable[[dict[str, Any]], bool],
) -> list[dict[str, Any]]:
    matching = [v for v in vehicles if predicate(v)]
    matching.sort(key=lambda v: rank_key(v, annual_miles))
    return matching[:size]


def has_strict_separation(
    vehicles: list[dict[str, Any]],
    annual_miles: int,
    size: int,
    predicate: Callable[[dict[str, Any]], bool],
) -> bool:
    """True when the size-th best candidate is strictly cheaper than the next one.

    Without this, two vehicles tie on TCO at the cut line and the "correct"
    shortlist depends on a VIN tiebreak the agent has no way to infer. Tasks
    that fail this check are rejected at build time rather than punishing the
    policy for an ambiguity we created.
    """
    from .. import tco as tco_mod

    matching = [v for v in vehicles if predicate(v)]
    if len(matching) <= size:
        return len(matching) == size
    matching.sort(key=lambda v: rank_key(v, annual_miles))
    inside = tco_mod.tco_5yr(matching[size - 1], annual_miles=annual_miles)
    outside = tco_mod.tco_5yr(matching[size], annual_miles=annual_miles)
    return outside > inside


def shortlist_payload(
    vehicles: list[dict[str, Any]], annual_miles: int, updated_by: str = "system"
) -> dict[str, Any]:
    """A well-formed `shortlist.json` for a ranked list of vehicles."""
    from .. import tco as tco_mod

    entries = []
    for rank, vehicle in enumerate(vehicles, start=1):
        cost = tco_mod.tco_5yr(vehicle, annual_miles=annual_miles)
        entries.append(
            {
                "rank": rank,
                "vin": vehicle["vin"],
                "tco_5yr": cost,
                "rationale": (
                    f"{vehicle['year']} {vehicle['make']} {vehicle['model']} — meets the stated "
                    f"requirements at a five-year cost of ownership of ${cost:,}."
                ),
            }
        )
    return {"updated_by": updated_by, "entries": entries}
