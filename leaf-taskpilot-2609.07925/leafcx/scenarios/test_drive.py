"""Family: book a test drive, and clear the slot it needs first.

No date arithmetic — the customer names the day and time. The work is in the
constraints around it: the booking must be for the *shortlist's* top pick rather
than the cheapest car, at that vehicle's own lot, and the two-appointment
ceiling means something has to be cancelled before anything can be booked.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .. import constraints as C
from . import base

SHORTLIST_SIZE = 3

#: Valid slots under `policies/booking.md`: Tuesday-Saturday, on the hour,
#: 09:00-16:00. Listed explicitly so no part of the stack has to compute them.
_SLOTS: tuple[str, ...] = (
    "2026-10-06T10:00:00",
    "2026-10-07T14:00:00",
    "2026-10-08T09:00:00",
    "2026-10-09T15:00:00",
    "2026-10-10T11:00:00",
    "2026-10-13T16:00:00",
    "2026-10-14T13:00:00",
)

_EXISTING_SLOTS: tuple[str, ...] = ("2026-09-29T10:00:00", "2026-09-30T15:00:00")


class TestDriveScenario(base.Scenario):
    family = "test_drive"
    summary = "Cancel an unwanted appointment and book the top pick at the right lot."

    def build(self, seed: int, hint_level: int = 0) -> base.TaskInstance:
        rng = random.Random(seed ^ 0xD81E)
        inventory = base.build_inventory(seed)
        annual_miles = rng.choice([10000, 12000, 14000])

        seeded = self._draw_shortlist(rng, inventory, annual_miles)
        target = seeded[0]
        # The two existing bookings are for ranks 2 and 3, so the top pick is
        # free and the ceiling is already reached.
        cancel_vehicle = seeded[rng.choice([1, 2])]
        keep_vehicle = next(v for v in seeded[1:] if v["vin"] != cancel_vehicle["vin"])
        requested_slot = rng.choice(_SLOTS)

        existing = []
        for index, vehicle in enumerate((seeded[1], seeded[2])):
            existing.append(
                {
                    "id": f"APT-{index + 1}",
                    "vin": vehicle["vin"],
                    "location": vehicle["location"],
                    "start": _EXISTING_SLOTS[index],
                    "status": "booked",
                }
            )

        params = {
            "annual_miles": annual_miles,
            "seeded_vins": [v["vin"] for v in seeded],
            "target_vin": target["vin"],
            "target_location": target["location"],
            "requested_slot": requested_slot,
            "cancel_vin": cancel_vehicle["vin"],
            "cancel_id": next(a["id"] for a in existing if a["vin"] == cancel_vehicle["vin"]),
            "keep_vin": keep_vehicle["vin"],
            "keep_id": next(a["id"] for a in existing if a["vin"] == keep_vehicle["vin"]),
            "keep_start": next(a["start"] for a in existing if a["vin"] == keep_vehicle["vin"]),
            "existing": existing,
        }

        day = requested_slot[:10]
        clock = requested_slot[11:16]
        brief = base.assemble_brief(
            headline="Swap one of my test drives",
            customer_words=(
                f"Drop the appointment for the {cancel_vehicle['year']} "
                f"{cancel_vehicle['make']} {cancel_vehicle['model']} — I've gone off it. "
                f"Book me in for whatever is sitting at the top of my shortlist instead, "
                f"on {day} at {clock}. Leave my other appointment alone, that one I still want."
            ),
            hint_level=hint_level,
            localising=(
                "Appointments live in `account/appointments.json`; `policies/booking.md` has "
                "the shape and the rules. Cancelling means setting `status` to `\"cancelled\"`, "
                "not deleting the entry — and you have to do it before the new booking fits "
                "under the open-appointment ceiling. The lot is whatever `location` the "
                "vehicle has in inventory; do not assume it is the customer's usual one."
            ),
            procedural=(
                f"1. `read account/appointments.json` and set `{params['cancel_id']}` to "
                '`"cancelled"`.\n'
                "2. `read account/shortlist.json` and take the rank-1 VIN.\n"
                "3. Look that VIN up with `search_inventory` to get its `location`.\n"
                f"4. Append a booking: that VIN, that location, "
                f'`start` `"{requested_slot}"`, `status` `"booked"`.\n'
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
                "which": "The top one on my shortlist.",
                "when": f"{day} at {clock}.",
                "cancel": (
                    f"The {cancel_vehicle['year']} {cancel_vehicle['make']} "
                    f"{cancel_vehicle['model']} one."
                ),
                "other": "Keep the other appointment exactly as it is.",
            },
        )

    def _draw_shortlist(
        self, rng: random.Random, inventory: list[dict[str, Any]], annual_miles: int
    ) -> list[dict[str, Any]]:
        """A three-vehicle shortlist, preferring one spread across two lots.

        Re-rolling the budget alone is not enough variety: the top three by TCO
        under a given budget are deterministic, so a lot where they share a
        location would loop forever. Vary the constraint shape instead, and fall
        back to a single-lot shortlist rather than failing to build the task --
        the agent still has to look the location up rather than assume it.
        """
        fallback: list[dict[str, Any]] | None = None
        options = [
            {"budget_max": budget, "max_accidents": accidents, **extra}
            for budget in (14000, 18000, 22000, 26000)
            for accidents in (0, 1)
            for extra in ({}, {"min_year": 2021}, {"exclude_fuel": ["electric"]})
        ]
        rng.shuffle(options)
        for constraints in options:
            seeded = base.pick_shortlist(
                inventory, annual_miles, SHORTLIST_SIZE, lambda v: C.matches(v, constraints)
            )
            if len(seeded) < SHORTLIST_SIZE:
                continue
            if fallback is None:
                fallback = seeded
            if len({v["location"] for v in seeded}) >= 2:
                return seeded
        if fallback is not None:
            return fallback
        raise RuntimeError("could not draw a well-posed test_drive task")

    def materialize(self, task: base.TaskInstance, root: Path) -> None:
        params = task.params
        inventory = base.build_inventory(task.seed)
        by_vin = {v["vin"]: v for v in inventory}
        seeded = [by_vin[vin] for vin in params["seeded_vins"]]
        profile = base.default_profile(task.seed, annual_miles=params["annual_miles"])
        overrides = {
            "shortlist.json": base.shortlist_payload(seeded, params["annual_miles"]),
            "appointments.json": {"appointments": [dict(a) for a in params["existing"]]},
        }
        base.materialize_common(root, task, inventory, profile, overrides)

    def solve(self, task: base.TaskInstance, root: Path) -> None:
        params = task.params
        path = root / "account" / "appointments.json"
        data = json.loads(path.read_text())
        for appointment in data["appointments"]:
            if appointment["id"] == params["cancel_id"]:
                appointment["status"] = "cancelled"
        data["appointments"].append(
            {
                "id": f"APT-{len(data['appointments']) + 1}",
                "vin": params["target_vin"],
                "location": params["target_location"],
                "start": params["requested_slot"],
                "status": "booked",
            }
        )
        path.write_text(json.dumps(data, indent=2) + "\n")

    def _hidden_tests(self, params: dict[str, Any]) -> str:
        body = '''
def appointments():
    data = load("account/appointments.json", {"appointments": []}) or {"appointments": []}
    return [a for a in data.get("appointments", []) if isinstance(a, dict)]


def booked():
    return [a for a in appointments() if a.get("status") == "booked"]


def test_f2p_unwanted_appointment_cancelled():
    matching = [a for a in appointments() if a.get("id") == PARAMS["cancel_id"]]
    assert matching, "the cancelled appointment was deleted instead of marked cancelled"
    assert matching[0].get("status") == "cancelled"


def test_f2p_top_pick_is_booked_at_the_right_lot_and_time():
    hits = [
        a
        for a in booked()
        if a.get("vin") == PARAMS["target_vin"] and a.get("start") == PARAMS["requested_slot"]
    ]
    assert hits, (
        f"expected a booked appointment for {PARAMS['target_vin']} at {PARAMS['requested_slot']}"
    )
    assert hits[0].get("location") == PARAMS["target_location"], (
        "the test drive has to happen at the lot holding that vehicle"
    )


def test_p2p_other_appointment_untouched():
    kept = [a for a in appointments() if a.get("id") == PARAMS["keep_id"]]
    assert kept, "the appointment the customer wanted kept is gone"
    assert kept[0].get("status") == "booked"
    assert kept[0].get("start") == PARAMS["keep_start"]
    assert kept[0].get("vin") == PARAMS["keep_vin"]


def test_p2p_open_appointment_ceiling_respected():
    assert len(booked()) <= policy.MAX_OPEN_APPOINTMENTS


def test_p2p_shortlist_untouched():
    assert shortlist_vins() == PARAMS["seeded_vins"]
'''
        return base.hidden_test_module(params, body)
