"""Family: apply an appraised trade-in to the budget and rebuild the shortlist.

The appraisal itself arrives from the inspection team, already in
`account/trade_in.json` — the agent's job is to apply it, not to price a car it
has never seen. What it has to get right is that the new ceiling is
cash + offer, that the old list is rebuilt against that ceiling rather than
patched, and that the appraisal record is left alone.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .. import constraints as C
from .. import tco as tco_mod
from . import base

SHORTLIST_SIZE = 3

#: Plausible trade-ins: models that were actually on sale in these years. Reusing
#: the current-lot catalogue produced things like a 2012 Ioniq 5.
LEGACY_TRADE_INS: tuple[tuple[int, str, str, str], ...] = (
    (2012, "Honda", "Civic", "sedan"),
    (2013, "Toyota", "Corolla", "sedan"),
    (2013, "Ford", "Focus", "hatchback"),
    (2014, "Honda", "CR-V", "suv"),
    (2014, "Nissan", "Altima", "sedan"),
    (2015, "Toyota", "Camry", "sedan"),
    (2015, "Subaru", "Outback", "wagon"),
    (2016, "Mazda", "Mazda3", "hatchback"),
    (2016, "Chevrolet", "Malibu", "sedan"),
    (2016, "Ford", "Escape", "suv"),
)


class TradeInScenario(base.Scenario):
    family = "trade_in"
    summary = "Fold an appraised trade-in into the budget and rebuild the shortlist."

    def build(self, seed: int, hint_level: int = 0) -> base.TaskInstance:
        rng = random.Random(seed ^ 0x7A4D)
        inventory = base.build_inventory(seed)
        annual_miles = rng.choice([10000, 12000, 15000])

        trade, cash_budget, offer_value, min_year, old_picks, new_picks = self._draw_task(
            rng, inventory, annual_miles
        )
        new_budget = cash_budget + offer_value

        params = {
            "annual_miles": annual_miles,
            "cash_budget": cash_budget,
            "offer_value": offer_value,
            "new_budget": new_budget,
            "trade_vehicle": trade,
            "seeded_vins": [v["vin"] for v in old_picks],
            "expected_vins": [v["vin"] for v in new_picks],
            "expected_tco": [tco_mod.tco_5yr(v, annual_miles=annual_miles) for v in new_picks],
            "min_year": min_year,
            "constraints": {
                "budget_max": new_budget,
                "max_accidents": 1,
                "min_year": min_year,
            },
        }

        brief = base.assemble_brief(
            headline="Use my trade-in",
            customer_words=(
                f"Your team looked at my {trade['year']} {trade['make']} {trade['model']} "
                f"({trade['mileage']:,} miles) and the offer is in my account. I want that "
                f"money working for me: my cash budget is ${cash_budget:,}, so add the trade "
                "on top and show me the best three I can actually get now. Same ground rules "
                f"as before — {min_year} or newer, and nothing with more than one accident "
                "on the report."
            ),
            hint_level=hint_level,
            localising=(
                "The appraisal is in `account/trade_in.json`; mark it applied once you have "
                "used it, and leave `offer_value` exactly as the appraiser set it. The new "
                "ceiling goes in `account/profile.json` as `budget_max`. Rebuild "
                "`account/shortlist.json` from scratch against the new ceiling — see "
                "`policies/shortlist.md` for the ranking rule."
            ),
            procedural=(
                f"1. `read account/trade_in.json` — the offer is ${offer_value:,}.\n"
                f"2. Set `budget_max` to {new_budget} in `account/profile.json`.\n"
                '3. Set `status` to `"applied"` in `account/trade_in.json`.\n'
                f"4. `search_inventory(max_price={new_budget}, min_year={min_year}, "
                'max_accidents=1, sort_by="tco_5yr")`.\n'
                f"5. Rewrite `account/shortlist.json` with the {SHORTLIST_SIZE} cheapest by "
                "`tco_5yr`.\n"
                "6. `validate_account`, then `bash python3 -m pytest -q tests/`."
            ),
        )

        return base.TaskInstance(
            task_id=f"{self.family}-{seed}-h{hint_level}",
            family=self.family,
            seed=seed,
            hint_level=hint_level,
            brief=brief,
            params=params,
            hidden_test_source=self._hidden_tests(params),
            customer_facts={
                "offer": f"Whatever the appraiser wrote down — ${offer_value:,}, I think.",
                "cash": f"${cash_budget:,} in cash, plus the trade.",
                "accidents": f"One accident max, and {min_year} or newer.",
            },
        )

    def _draw_task(
        self, rng: random.Random, inventory: list[dict[str, Any]], annual_miles: int
    ) -> tuple[dict[str, Any], int, int, int, list[dict[str, Any]], list[dict[str, Any]]]:
        """Draw a trade-in large enough that the shortlist genuinely changes.

        A budget-only constraint would make this task vacuous: the TCO-cheapest
        cars on the lot are also among the cheapest to buy, so raising the
        ceiling never changes the optimum. Pinning a model-year floor puts the
        efficient vehicles above the cash budget, which is what makes the trade
        worth applying.
        """
        for _ in range(600):
            min_year = rng.choice([2021, 2022])
            cash_budget = rng.choice([7500, 9000, 10500, 12000])
            offer_value = rng.choice([3500, 4500, 6000, 7500])
            new_budget = cash_budget + offer_value

            old_constraints = {"budget_max": cash_budget, "max_accidents": 1, "min_year": min_year}
            new_constraints = {"budget_max": new_budget, "max_accidents": 1, "min_year": min_year}
            old_picks = base.pick_shortlist(
                inventory, annual_miles, SHORTLIST_SIZE, lambda v: C.matches(v, old_constraints)
            )
            new_picks = base.pick_shortlist(
                inventory, annual_miles, SHORTLIST_SIZE, lambda v: C.matches(v, new_constraints)
            )
            if len(old_picks) < SHORTLIST_SIZE or len(new_picks) < SHORTLIST_SIZE:
                continue
            if [v["vin"] for v in old_picks] == [v["vin"] for v in new_picks]:
                # The trade buys nothing new; the task would be "do nothing".
                continue
            if not base.has_strict_separation(
                inventory, annual_miles, SHORTLIST_SIZE, lambda v: C.matches(v, new_constraints)
            ):
                continue
            year, make, model, body = rng.choice(LEGACY_TRADE_INS)
            trade = {
                "year": year,
                "make": make,
                "model": model,
                "body_style": body,
                "mileage": rng.choice([96000, 112000, 128000, 143000, 158000]),
                "condition": rng.choice(["fair", "good", "good", "very good"]),
            }
            return trade, cash_budget, offer_value, min_year, old_picks, new_picks
        raise RuntimeError("could not draw a well-posed trade_in task")

    def materialize(self, task: base.TaskInstance, root: Path) -> None:
        params = task.params
        inventory = base.build_inventory(task.seed)
        by_vin = {v["vin"]: v for v in inventory}
        seeded = [by_vin[vin] for vin in params["seeded_vins"]]
        profile = base.default_profile(
            task.seed,
            annual_miles=params["annual_miles"],
            budget_max=params["cash_budget"],
        )
        overrides = {
            "shortlist.json": base.shortlist_payload(seeded, params["annual_miles"]),
            "trade_in.json": {
                "status": "appraised",
                "appraised_at": "2026-09-18T14:20:00",
                "appraiser": "Fremont inspection bay",
                "vehicle": params["trade_vehicle"],
                "offer_value": params["offer_value"],
                "offer_expires": "2026-10-18",
            },
        }
        base.materialize_common(root, task, inventory, profile, overrides)

    def solve(self, task: base.TaskInstance, root: Path) -> None:
        params = task.params
        profile = json.loads((root / "account" / "profile.json").read_text())
        profile["budget_max"] = params["new_budget"]
        (root / "account" / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")

        trade = json.loads((root / "account" / "trade_in.json").read_text())
        trade["status"] = "applied"
        (root / "account" / "trade_in.json").write_text(json.dumps(trade, indent=2) + "\n")

        inventory = json.loads((root / "inventory" / "vehicles.json").read_text())
        by_vin = {v["vin"]: v for v in inventory}
        picks = [by_vin[vin] for vin in params["expected_vins"]]
        payload = base.shortlist_payload(picks, params["annual_miles"], updated_by="agent")
        (root / "account" / "shortlist.json").write_text(json.dumps(payload, indent=2) + "\n")

    def _hidden_tests(self, params: dict[str, Any]) -> str:
        body = '''
def trade():
    return load("account/trade_in.json", {}) or {}


def test_f2p_budget_includes_the_trade():
    profile = load("account/profile.json", {}) or {}
    assert profile.get("budget_max") == PARAMS["new_budget"], (
        "the new ceiling is cash budget plus the appraised offer"
    )


def test_f2p_trade_marked_applied():
    assert trade().get("status") == "applied"


def test_f2p_shortlist_rebuilt_against_the_new_budget():
    assert shortlist_vins() == PARAMS["expected_vins"]


def test_f2p_shortlist_reports_the_inventory_tco():
    assert [e.get("tco_5yr") for e in shortlist_entries()] == PARAMS["expected_tco"]


def test_p2p_appraisal_not_edited():
    record = trade()
    assert record.get("offer_value") == PARAMS["offer_value"], "the appraisal is not ours to change"
    assert record.get("vehicle") == PARAMS["trade_vehicle"]


def test_p2p_picks_respect_the_constraints():
    from leafcx import constraints as C

    by_vin = account.inventory_by_vin(ROOT)
    for vin in shortlist_vins():
        assert vin in by_vin, f"unknown VIN {vin}"
        assert C.matches(by_vin[vin], PARAMS["constraints"])


def test_p2p_audit_log_preserved():
    log = load("account/audit_log.json", {"events": []}) or {"events": []}
    assert any(e.get("event") == "account_created" for e in log.get("events", [])), (
        "audit log entries are append-only"
    )
'''
        return base.hidden_test_module(params, body)
