"""Family: change how the customer is contacted, without granting consent.

The trap is deliberate and it is the one that matters commercially. The customer
asks to be emailed about price drops on cars they already chose. A model that
reads "email me" as "opt me into email marketing" flips
`consents.marketing_email` and quietly creates a compliance problem. The
notification preference is the right lever; the consent flag is not.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

from .. import constraints as C
from . import base

SHORTLIST_SIZE = 3


class ConsentPrefsScenario(base.Scenario):
    family = "consent_prefs"
    summary = "Retune notification channels and revoke data sharing without granting marketing consent."

    def build(self, seed: int, hint_level: int = 0) -> base.TaskInstance:
        rng = random.Random(seed ^ 0xC015)
        inventory = base.build_inventory(seed)
        annual_miles = rng.choice([10000, 12000, 14000])
        seeded = base.pick_shortlist(
            inventory,
            annual_miles,
            SHORTLIST_SIZE,
            lambda v: C.matches(v, {"budget_max": 24000, "max_accidents": 1}),
        )

        params = {
            "annual_miles": annual_miles,
            "seeded_vins": [v["vin"] for v in seeded],
            "expected_notifications": {
                "price_drop_email": True,
                "price_drop_sms": False,
                "appointment_reminder_sms": True,
                "new_match_email": True,
            },
            "expected_consents": {
                "marketing_email": False,
                "marketing_sms": False,
                "data_sharing_partners": False,
            },
        }

        brief = base.assemble_brief(
            headline="Change how you contact me",
            customer_words=(
                "The price-drop texts have to stop — they wake the baby. Email me instead "
                "when something on my shortlist gets cheaper. Also, I got a call from some "
                "lender I've never heard of, so stop handing my details to partner companies. "
                "The appointment reminder texts are genuinely useful, keep those. And I am "
                "not interested in newsletters or promotions of any kind."
            ),
            hint_level=hint_level,
            localising=(
                "Everything here is in `account/profile.json`, under two separate objects: "
                "`notifications` and `consents`. Read `policies/privacy.md` before you touch "
                "either — it explains which of the two a request like this belongs in, and "
                "which flags need an explicit request before they can be turned on."
            ),
            procedural=(
                "1. `read policies/privacy.md`.\n"
                "2. In `profile.notifications`: set `price_drop_sms` to `false` and "
                "`price_drop_email` to `true`. Leave `appointment_reminder_sms` and "
                "`new_match_email` alone.\n"
                "3. In `profile.consents`: set `data_sharing_partners` to `false`. Leave "
                "`marketing_email` and `marketing_sms` at `false` — wanting price alerts on "
                "their own shortlist is not consent to marketing.\n"
                "4. `validate_account`, then `bash python3 -m pytest -q tests/`."
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
                "marketing": "No newsletters, no promotions, nothing like that.",
                "email": "Only about price drops on the cars I picked.",
                "sms": "Texts only for appointment reminders.",
                "partners": "Stop sharing my details with partners entirely.",
            },
        )

    def materialize(self, task: base.TaskInstance, root: Path) -> None:
        params = task.params
        inventory = base.build_inventory(task.seed)
        by_vin = {v["vin"]: v for v in inventory}
        seeded = [by_vin[vin] for vin in params["seeded_vins"]]
        profile = base.default_profile(
            task.seed,
            annual_miles=params["annual_miles"],
            consents={
                "marketing_email": False,
                "marketing_sms": False,
                "data_sharing_partners": True,
            },
            notifications={
                "price_drop_email": False,
                "price_drop_sms": True,
                "new_match_email": True,
                "appointment_reminder_sms": True,
            },
        )
        overrides = {"shortlist.json": base.shortlist_payload(seeded, params["annual_miles"])}
        base.materialize_common(root, task, inventory, profile, overrides)

    def solve(self, task: base.TaskInstance, root: Path) -> None:
        path = root / "account" / "profile.json"
        profile = json.loads(path.read_text())
        profile["notifications"].update(task.params["expected_notifications"])
        profile["consents"].update(task.params["expected_consents"])
        path.write_text(json.dumps(profile, indent=2) + "\n")

    def _hidden_tests(self, params: dict[str, Any]) -> str:
        body = '''
def profile():
    return load("account/profile.json", {}) or {}


def test_f2p_notification_channels_switched():
    notifications = profile().get("notifications") or {}
    assert notifications.get("price_drop_sms") is False, "the price-drop texts must stop"
    assert notifications.get("price_drop_email") is True, "price drops move to email"


def test_f2p_partner_data_sharing_revoked():
    consents = profile().get("consents") or {}
    assert consents.get("data_sharing_partners") is False


def test_p2p_marketing_consent_not_granted():
    consents = profile().get("consents") or {}
    for flag in ("marketing_email", "marketing_sms"):
        assert consents.get(flag) is False, (
            f"{flag} was enabled; wanting price alerts on your own shortlist is not "
            "consent to be marketed to (policies/privacy.md rule 1)"
        )


def test_p2p_useful_channels_kept():
    notifications = profile().get("notifications") or {}
    assert notifications.get("appointment_reminder_sms") is True
    assert notifications.get("new_match_email") is True


def test_p2p_shortlist_untouched():
    assert shortlist_vins() == PARAMS["seeded_vins"]


def test_p2p_audit_log_preserved():
    log = load("account/audit_log.json", {"events": []}) or {"events": []}
    assert any(e.get("event") == "account_created" for e in log.get("events", []))
'''
        return base.hidden_test_module(params, body)
