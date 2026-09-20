"""Flagship family: build a ranked shortlist from a customer's stated needs.

This is the account-management analogue of the paper's headline SWE task. The
agent has to read the policy, translate prose into filters, search the lot, rank
by five-year cost rather than sticker price, and write a well-formed file.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .. import constraints as C
from .. import policy
from .. import tco as tco_mod
from . import base

SHORTLIST_SIZE = 3

#: Life situations that generate a coherent constraint bundle.
_PERSONAS: tuple[dict[str, Any], ...] = (
    {
        "key": "growing_family",
        "words": (
            "We've got a second kid on the way, so we need something with room for "
            "car seats and a stroller. No two-doors. I'd rather not go electric — we "
            "park on the street and there's nowhere to plug in."
        ),
        "constraints": {"min_seats": 5, "exclude_fuel": ["electric"], "body_styles": ["suv", "minivan", "wagon"]},
        "annual_miles": 11000,
    },
    {
        "key": "long_commute",
        "words": (
            "I'm driving 90 miles round trip to Livermore five days a week. Fuel is "
            "killing me. I don't care what it looks like, I care what it costs me "
            "over the next five years."
        ),
        "constraints": {"body_styles": ["sedan", "hatchback"]},
        "annual_miles": 23000,
    },
    {
        "key": "first_car",
        "words": (
            "First car, I'm 23, my insurance is already awful. Nothing that's been in "
            "a crash, and I'd like it to be recent enough that it isn't falling apart."
        ),
        "constraints": {"max_accidents": 0, "min_year": 2021},
        "annual_miles": 9000,
    },
    {
        "key": "contractor",
        "words": (
            "I haul tools and lumber for work. Needs to be a truck, needs all-wheel or "
            "four-wheel drive, and I'd rather buy certified so I'm not eating repair "
            "bills in year one."
        ),
        "constraints": {"body_styles": ["truck"], "certified_only": True},
        "annual_miles": 16000,
    },
    {
        "key": "downsizing",
        "words": (
            "Kids are gone, we want to get out of the big SUV. Something small and "
            "cheap to run. We have a garage with a plug, so electric is fine — good, "
            "actually — as long as it does at least 200 miles."
        ),
        "constraints": {"body_styles": ["hatchback", "sedan"], "min_year": 2020},
        "annual_miles": 8000,
    },
)


class ShortlistScenario(base.Scenario):
    family = "shortlist_build"
    summary = "Translate a customer's needs into filters and write a TCO-ranked shortlist."

    def build(self, seed: int, hint_level: int = 0) -> base.TaskInstance:
        rng = random.Random(seed)
        inventory = base.build_inventory(seed)

        persona, constraints, annual_miles = self._draw_task(rng, inventory)
        gold = base.pick_shortlist(
            inventory,
            annual_miles,
            SHORTLIST_SIZE,
            lambda v: C.matches(v, constraints),
        )

        params = {
            "constraints": constraints,
            "annual_miles": annual_miles,
            "shortlist_size": SHORTLIST_SIZE,
            "persona": persona["key"],
            "expected_vins": [v["vin"] for v in gold],
            "expected_tco": [tco_mod.tco_5yr(v, annual_miles=annual_miles) for v in gold],
        }

        brief = base.assemble_brief(
            headline="Build my shortlist",
            customer_words=(
                f"{persona['words']}\n\n"
                f"My hard limits: {C.as_sentence(constraints)}.\n\n"
                f"I drive about {annual_miles:,} miles a year. Give me your top "
                f"{SHORTLIST_SIZE} and tell me why each one is on the list."
            ),
            hint_level=hint_level,
            localising=(
                "Write `account/shortlist.json`. Read `policies/shortlist.md` first — it "
                "fixes the ranking rule and the required fields. `search_inventory` "
                "reports `tco_5yr` for every vehicle; copy that number, do not recompute it."
            ),
            procedural=(
                f"1. `read policies/shortlist.md`.\n"
                f"2. `search_inventory` with every hard limit above as a filter, "
                f"`sort_by=\"tco_5yr\"`.\n"
                f"3. Take the {SHORTLIST_SIZE} cheapest by `tco_5yr`.\n"
                f"4. `write account/shortlist.json` with `rank` 1..{SHORTLIST_SIZE}, `vin`, "
                f"`tco_5yr` and a `rationale` of at least "
                f"{policy.MIN_RATIONALE_CHARS} characters.\n"
                f"5. `validate_account`, then `bash python3 -m pytest -q tests/`."
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
                "budget": f"I can't go over ${constraints['budget_max']:,}.",
                "fuel": persona["words"],
                "miles": f"About {annual_miles:,} miles a year.",
                "seats": f"At least {constraints.get('min_seats', 4)} seats.",
            },
        )

    def _draw_task(
        self, rng: random.Random, inventory: list[dict[str, Any]]
    ) -> tuple[dict[str, Any], dict[str, Any], int]:
        """Draw a persona and a budget that yields a well-posed task.

        Well-posed means: enough candidates that filtering is real work, few
        enough that the answer is not "everything", and a strict TCO gap at the
        cut line so the correct shortlist is unambiguous.
        """
        for _ in range(200):
            persona = rng.choice(_PERSONAS)
            constraints = dict(persona["constraints"])
            annual_miles = persona["annual_miles"]
            constraints["budget_max"] = rng.choice(
                [12000, 14000, 16000, 18000, 20000, 22000, 24000, 26000]
            )
            if rng.random() < 0.5:
                constraints["max_mileage"] = rng.choice([60000, 75000, 90000, 110000])
            if rng.random() < 0.35 and "min_year" not in constraints:
                constraints["min_year"] = rng.choice([2019, 2020, 2021])

            matching = [v for v in inventory if C.matches(v, constraints)]
            if not 4 <= len(matching) <= 70:
                continue
            if not base.has_strict_separation(
                inventory, annual_miles, SHORTLIST_SIZE, lambda v: C.matches(v, constraints)
            ):
                continue
            return persona, constraints, annual_miles
        raise RuntimeError("could not draw a well-posed shortlist task; widen the budget ladder")

    def materialize(self, task: base.TaskInstance, root: Path) -> None:
        inventory = base.build_inventory(task.seed)
        profile = base.default_profile(
            task.seed,
            annual_miles=task.params["annual_miles"],
            budget_max=task.params["constraints"]["budget_max"],
        )
        base.materialize_common(root, task, inventory, profile)

    def solve(self, task: base.TaskInstance, root: Path) -> None:
        inventory = json.loads((root / "inventory" / "vehicles.json").read_text())
        by_vin = {v["vin"]: v for v in inventory}
        entries = []
        for rank, (vin, cost) in enumerate(
            zip(task.params["expected_vins"], task.params["expected_tco"]), start=1
        ):
            vehicle = by_vin[vin]
            entries.append(
                {
                    "rank": rank,
                    "vin": vin,
                    "tco_5yr": cost,
                    "rationale": (
                        f"{vehicle['year']} {vehicle['make']} {vehicle['model']} — meets every "
                        f"hard requirement and has the #{rank} lowest five-year cost of ownership "
                        f"(${cost:,}) among the vehicles that qualify."
                    ),
                }
            )
        (root / "account" / "shortlist.json").write_text(
            json.dumps({"updated_by": "agent", "entries": entries}, indent=2) + "\n"
        )

    def _hidden_tests(self, params: dict[str, Any]) -> str:
        body = '''
def test_f2p_shortlist_has_the_right_vehicles_in_the_right_order():
    assert shortlist_vins() == PARAMS["expected_vins"], (
        "shortlist must hold exactly the qualifying vehicles with the lowest "
        "five-year TCO, ranked cheapest first"
    )


def test_f2p_shortlist_reports_the_inventory_tco():
    entries = shortlist_entries()
    assert [e.get("tco_5yr") for e in entries] == PARAMS["expected_tco"]


def test_p2p_every_pick_satisfies_the_hard_constraints():
    from leafcx import constraints as C

    by_vin = account.inventory_by_vin(ROOT)
    for entry in shortlist_entries():
        vehicle = by_vin.get(entry.get("vin"))
        assert vehicle is not None, f"unknown VIN {entry.get('vin')}"
        assert C.matches(vehicle, PARAMS["constraints"]), (
            f"{entry['vin']} violates a hard constraint"
        )


def test_p2p_rationales_are_substantive():
    for entry in shortlist_entries():
        rationale = (entry.get("rationale") or "").strip()
        assert len(rationale) >= policy.MIN_RATIONALE_CHARS, (
            f"rationale for {entry.get('vin')} is too short"
        )


def test_p2p_profile_was_not_rewritten():
    profile = load("account/profile.json", {}) or {}
    assert profile.get("annual_miles") == PARAMS["annual_miles"]
    assert profile.get("customer_id"), "customer_id was removed from the profile"
'''
        return base.hidden_test_module(params, body)
