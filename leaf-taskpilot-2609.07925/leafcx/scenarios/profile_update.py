"""Family: a life change moves the constraints, and the account has to follow.

Tests propagation rather than search. The customer changes one thing; three
files have to end up consistent with it, and the entries that no longer qualify
have to come off the list without disturbing the ones that still do.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .. import constraints as C
from .. import tco as tco_mod
from . import base

INITIAL_SHORTLIST_SIZE = 5

_WORDS = (
    "My hours got cut at work. I need to pull the top of my budget down to "
    "${new_budget:,} — anything above that is off the table now."
)


class ProfileUpdateScenario(base.Scenario):
    family = "profile_update"
    summary = "Propagate a budget change through the profile, saved search and shortlist."

    def build(self, seed: int, hint_level: int = 0) -> base.TaskInstance:
        rng = random.Random(seed ^ 0x5EED)
        inventory = base.build_inventory(seed)
        annual_miles = rng.choice([9000, 12000, 15000])

        old_budget, new_budget, seeded, survivors = self._draw_task(rng, inventory, annual_miles)

        params = {
            "old_budget": old_budget,
            "new_budget": new_budget,
            "annual_miles": annual_miles,
            "seeded_vins": [v["vin"] for v in seeded],
            "expected_vins": [v["vin"] for v in survivors],
            "expected_tco": [tco_mod.tco_5yr(v, annual_miles=annual_miles) for v in survivors],
            "change": "budget_cut",
        }

        brief = base.assemble_brief(
            headline="My budget changed",
            customer_words=(
                _WORDS.format(new_budget=new_budget)
                + "\n\nPlease fix my profile and the saved search that emails me matches, "
                "and take anything off my shortlist that no longer fits. Keep the rest "
                f"in the same order. Don't add new cars — I've only got time to look at "
                "what I already picked."
            ),
            hint_level=hint_level,
            localising=(
                "Three files: `account/profile.json` (`budget_max`), "
                "`account/saved_searches.json` (the search's `filters.max_price`), and "
                "`account/shortlist.json`. After removing entries, `rank` must still run "
                "1..n with no gaps — see `policies/shortlist.md`."
            ),
            procedural=(
                f"1. Set `budget_max` to {new_budget} in `account/profile.json`.\n"
                f"2. Set `filters.max_price` to {new_budget} in the saved search.\n"
                "3. Look up each shortlisted VIN's price with `search_inventory` or by "
                "reading `inventory/vehicles.json`.\n"
                f"4. Drop every entry priced above {new_budget}, keep the rest in their "
                "existing order, and renumber `rank` from 1.\n"
                "5. `validate_account`, then `bash python3 -m pytest -q tests/`."
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
                "budget": f"${new_budget:,} is the new ceiling.",
                "add": "No, don't add anything new. Just clean up what's there.",
                "order": "Keep the ones that survive in the order they're already in.",
            },
        )

    def _draw_task(
        self, rng: random.Random, inventory: list[dict[str, Any]], annual_miles: int
    ) -> tuple[int, int, list[dict[str, Any]], list[dict[str, Any]]]:
        """Pick a shortlist and a budget cut that removes some but not all of it.

        The seeded shortlist has to span a price range near the old budget,
        otherwise the "cut" lands far below every entry and the task degenerates
        into deleting nothing or everything.
        """
        for _ in range(400):
            old_budget = rng.choice([18000, 20000, 22000, 24000, 26000])
            eligible = [
                v
                for v in inventory
                if C.matches(v, {"budget_max": old_budget, "max_accidents": 1})
                and v["price"] >= 0.55 * old_budget
            ]
            if len(eligible) < INITIAL_SHORTLIST_SIZE * 3:
                continue
            sample = rng.sample(eligible, INITIAL_SHORTLIST_SIZE)
            prices = sorted((v["price"] for v in sample), reverse=True)
            if len(set(prices)) != INITIAL_SHORTLIST_SIZE:
                continue
            cut_index = rng.randint(1, INITIAL_SHORTLIST_SIZE - 1)
            new_budget = int(prices[cut_index])
            survivors_all = [v for v in sample if v["price"] <= new_budget]
            if len(survivors_all) != INITIAL_SHORTLIST_SIZE - cut_index:
                continue
            # Seeded list is stored in policy order (ascending TCO); survivors
            # keep that relative order, which is what the brief asks for.
            sample.sort(key=lambda v: base.rank_key(v, annual_miles))
            survivors = [v for v in sample if v["price"] <= new_budget]
            return old_budget, new_budget, sample, survivors
        raise RuntimeError("could not draw a well-posed profile_update task")

    def materialize(self, task: base.TaskInstance, root: Path) -> None:
        inventory = base.build_inventory(task.seed)
        by_vin = {v["vin"]: v for v in inventory}
        seeded = [by_vin[vin] for vin in task.params["seeded_vins"]]
        profile = base.default_profile(
            task.seed,
            annual_miles=task.params["annual_miles"],
            budget_max=task.params["old_budget"],
        )
        overrides = {
            "shortlist.json": base.shortlist_payload(seeded, task.params["annual_miles"]),
            "saved_searches.json": {
                "searches": [
                    {
                        "id": "SS-1",
                        "name": "Daily driver",
                        "alerts": True,
                        "filters": {
                            "max_price": task.params["old_budget"],
                            "max_accidents": 1,
                            "sort_by": "tco_5yr",
                        },
                    }
                ]
            },
        }
        base.materialize_common(root, task, inventory, profile, overrides)

    def solve(self, task: base.TaskInstance, root: Path) -> None:
        params = task.params
        profile = json.loads((root / "account" / "profile.json").read_text())
        profile["budget_max"] = params["new_budget"]
        (root / "account" / "profile.json").write_text(json.dumps(profile, indent=2) + "\n")

        searches = json.loads((root / "account" / "saved_searches.json").read_text())
        searches["searches"][0]["filters"]["max_price"] = params["new_budget"]
        (root / "account" / "saved_searches.json").write_text(json.dumps(searches, indent=2) + "\n")

        shortlist = json.loads((root / "account" / "shortlist.json").read_text())
        kept = [e for e in shortlist["entries"] if e["vin"] in set(params["expected_vins"])]
        kept.sort(key=lambda e: params["expected_vins"].index(e["vin"]))
        for rank, entry in enumerate(kept, start=1):
            entry["rank"] = rank
        (root / "account" / "shortlist.json").write_text(
            json.dumps({"updated_by": "agent", "entries": kept}, indent=2) + "\n"
        )

    def _hidden_tests(self, params: dict[str, Any]) -> str:
        body = '''
def test_f2p_profile_budget_updated():
    profile = load("account/profile.json", {}) or {}
    assert profile.get("budget_max") == PARAMS["new_budget"]


def test_f2p_saved_search_updated():
    searches = (load("account/saved_searches.json", {"searches": []}) or {}).get("searches", [])
    assert searches, "the saved search was removed"
    assert searches[0].get("filters", {}).get("max_price") == PARAMS["new_budget"]


def test_f2p_shortlist_pruned_and_renumbered():
    assert shortlist_vins() == PARAMS["expected_vins"], (
        "keep exactly the entries that still fit the new budget, in their original order"
    )


def test_p2p_no_new_vehicles_were_added():
    assert set(shortlist_vins()) <= set(PARAMS["seeded_vins"]), (
        "the customer asked not to add new cars"
    )


def test_f2p_surviving_entries_kept_their_tco():
    entries = shortlist_entries()
    assert [e.get("tco_5yr") for e in entries] == PARAMS["expected_tco"]


def test_p2p_annual_miles_untouched():
    profile = load("account/profile.json", {}) or {}
    assert profile.get("annual_miles") == PARAMS["annual_miles"]
'''
        return base.hidden_test_module(params, body)
