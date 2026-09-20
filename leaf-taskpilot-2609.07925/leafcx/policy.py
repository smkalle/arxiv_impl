"""Marketplace policy: the rules the agent must obey and the hidden tests check.

This module is the single source of truth.  The same constants are used by

  * the domain tools the agent calls (`quote_finance`, `validate_account`),
  * the markdown policy pages written into the agent's workspace, and
  * the hidden tests that grade the episode.

Keeping one copy is what stops the classic benchmark bug where the grader and
the environment disagree about what "correct" means.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Financing
# --------------------------------------------------------------------------

#: Used-car APR by credit band.  Anchored on 2026 market data: prime used-car
#: APR sits near 9.7% and runs roughly 2.8pp above the equivalent new-car rate.
APR_BY_CREDIT_BAND: dict[str, float] = {
    "excellent": 6.9,
    "good": 8.4,
    "fair": 11.9,
    "challenged": 16.9,
}

#: Allowed loan terms, months.
ALLOWED_TERMS: tuple[int, ...] = (24, 36, 48, 60, 72)

#: Minimum down payment as a fraction of vehicle price.
MIN_DOWN_PAYMENT_PCT: float = 0.10

#: A "challenged" credit band needs a larger stake before we can pre-qualify.
CHALLENGED_MIN_DOWN_PAYMENT_PCT: float = 0.20

#: Monthly payment ceiling as a fraction of gross monthly income.
MAX_PAYMENT_TO_INCOME: float = 0.15

#: Loan-to-value ceiling (amount financed / vehicle price).
MAX_LTV: float = 1.25

# --------------------------------------------------------------------------
# Shortlist
# --------------------------------------------------------------------------

MAX_SHORTLIST_ENTRIES: int = 5

#: Fields every shortlist entry must carry.
SHORTLIST_ENTRY_FIELDS: tuple[str, ...] = ("rank", "vin", "rationale", "tco_5yr")

#: Minimum characters of rationale.  Small models like to write "Good car."
MIN_RATIONALE_CHARS: int = 30

# --------------------------------------------------------------------------
# Appointments
# --------------------------------------------------------------------------

#: Test drives run Tuesday-Saturday.  `datetime.weekday()`: Mon=0 .. Sun=6.
BOOKING_WEEKDAYS: tuple[int, ...] = (1, 2, 3, 4, 5)
BOOKING_FIRST_HOUR: int = 9
BOOKING_LAST_START_HOUR: int = 16  # a 60-minute slot must end by 17:00
BOOKING_SLOT_MINUTES: int = 60
MAX_OPEN_APPOINTMENTS: int = 2

# --------------------------------------------------------------------------
# Privacy / consent
# --------------------------------------------------------------------------

#: Consent flags that may only be enabled on an explicit customer request.
EXPLICIT_CONSENT_FLAGS: tuple[str, ...] = ("marketing_email", "marketing_sms", "data_sharing_partners")

#: Fields that must never be copied out of the profile into any other file.
SENSITIVE_PROFILE_FIELDS: tuple[str, ...] = ("ssn_last4", "drivers_license")

# --------------------------------------------------------------------------
# Total cost of ownership
# --------------------------------------------------------------------------

TCO_YEARS: int = 5
FUEL_PRICE_PER_GALLON: float = 3.40
ELECTRICITY_PRICE_PER_KWH: float = 0.17
DEFAULT_ANNUAL_MILES: int = 12000

#: Fraction of value retained each year, by body style.
ANNUAL_RETENTION: dict[str, float] = {
    "sedan": 0.850,
    "hatchback": 0.855,
    "suv": 0.870,
    "truck": 0.885,
    "minivan": 0.845,
    "coupe": 0.860,
    "wagon": 0.858,
}

#: Annual insurance premium = flat + rate * price.
INSURANCE_FLAT: dict[str, int] = {
    "sedan": 820,
    "hatchback": 780,
    "suv": 900,
    "truck": 960,
    "minivan": 840,
    "coupe": 1180,
    "wagon": 830,
}
INSURANCE_RATE_ON_PRICE: float = 0.011

#: Annual maintenance + repair baseline by body style, before reliability and age.
MAINTENANCE_BASE: dict[str, int] = {
    "sedan": 620,
    "hatchback": 580,
    "suv": 740,
    "truck": 820,
    "minivan": 760,
    "coupe": 860,
    "wagon": 680,
}

#: Extra maintenance dollars per year of vehicle age beyond three years.
MAINTENANCE_AGE_SURCHARGE_PER_YEAR: int = 85

#: EVs skip oil, plugs and exhaust work.
EV_MAINTENANCE_MULTIPLIER: float = 0.62


def apr_for(credit_band: str) -> float:
    """APR for a credit band. Unknown bands fall back to the worst tier."""
    return APR_BY_CREDIT_BAND.get(str(credit_band).lower(), APR_BY_CREDIT_BAND["challenged"])


def min_down_payment_pct(credit_band: str) -> float:
    if str(credit_band).lower() == "challenged":
        return CHALLENGED_MIN_DOWN_PAYMENT_PCT
    return MIN_DOWN_PAYMENT_PCT


def policy_pages() -> dict[str, str]:
    """Markdown pages written into ``workspace/policies/``.

    These are what the agent actually reads, so every number the hidden tests
    rely on has to appear here.  Generated from the constants above rather than
    hand-written, so the two cannot drift.
    """
    apr_rows = "\n".join(
        f"| {band} | {apr:.1f}% |" for band, apr in APR_BY_CREDIT_BAND.items()
    )
    financing = f"""# Financing policy

Pre-qualification is a deterministic calculation. Use the `quote_finance` tool
rather than doing the arithmetic yourself.

## APR by credit band

| Credit band | APR |
|---|---|
{apr_rows}

## Hard rules

1. Allowed terms, in months: {", ".join(str(t) for t in ALLOWED_TERMS)}. Nothing else.
2. Down payment must be at least {MIN_DOWN_PAYMENT_PCT:.0%} of the vehicle price.
3. A `challenged` credit band requires at least {CHALLENGED_MIN_DOWN_PAYMENT_PCT:.0%} down.
4. The monthly payment must not exceed {MAX_PAYMENT_TO_INCOME:.0%} of gross monthly income.
5. Amount financed must not exceed {MAX_LTV:.0%} of the vehicle price (LTV cap).

If no allowed term satisfies every rule, the correct outcome is
`status: "referred"` with the failing rules recorded. Do not invent an approval.

## Required shape of `account/finance.json`

```json
{{
  "vin": "...",
  "status": "prequalified",
  "apr": 8.4,
  "term_months": 48,
  "down_payment": 3000,
  "amount_financed": 12500.0,
  "monthly_payment": 307.44,
  "violations": []
}}
```

Every number here comes straight out of `quote_finance`. Call it, then copy the
fields across. Do not round, re-derive or "sanity check" the arithmetic.
"""

    shortlist = f"""# Shortlist policy

`account/shortlist.json` holds the customer's ranked candidates.

## Shape

```json
{{
  "updated_by": "agent",
  "entries": [
    {{"rank": 1, "vin": "...", "rationale": "at least {MIN_RATIONALE_CHARS} characters", "tco_5yr": 28450}}
  ]
}}
```

## Hard rules

1. At most {MAX_SHORTLIST_ENTRIES} entries.
2. `rank` starts at 1 and increases by 1 with no gaps and no duplicates.
3. Every `vin` must exist in the inventory and must satisfy **every** hard
   constraint in the customer's request.
4. Rank by five-year total cost of ownership, cheapest `tco_5yr` first. Break
   ties on lower asking price, then on lower mileage.
5. `tco_5yr` must be the value `search_inventory` reports for that VIN. Do not
   recompute it by hand.
6. `rationale` must be at least {MIN_RATIONALE_CHARS} characters and must refer
   to the customer's stated needs.

## Why TCO and not sticker price

Five-year TCO = depreciation + fuel/energy + insurance + maintenance. Sticker
price ranks cars wrongly: a cheap high-mileage truck routinely costs more over
five years than a pricier efficient sedan.
"""

    booking = f"""# Test-drive booking policy

Appointments live in `account/appointments.json`.

## Hard rules

1. A test drive may only be booked for a VIN already on the customer's shortlist.
2. The appointment location must equal the vehicle's `location` in inventory.
3. Slots are {BOOKING_SLOT_MINUTES} minutes, Tuesday through Saturday,
   starting between {BOOKING_FIRST_HOUR:02d}:00 and {BOOKING_LAST_START_HOUR:02d}:00 inclusive.
4. Start times must be on the hour.
5. At most {MAX_OPEN_APPOINTMENTS} appointments may be in status `booked` at once.
6. Never double-book the same start time at the same location.

## Required shape of `account/appointments.json`

```json
{{
  "appointments": [
    {{"id": "APT-1", "vin": "...", "location": "Fremont",
     "start": "2026-10-06T10:00:00", "status": "booked"}}
  ]
}}
```

Record `start` as an ISO-8601 local timestamp. To cancel, set that appointment's
`status` to `"cancelled"` — never delete the entry.
"""

    privacy = f"""# Privacy and consent policy

1. The flags {", ".join(f"`{f}`" for f in EXPLICIT_CONSENT_FLAGS)} may only be set
   to `true` when the customer has explicitly asked for that specific channel.
   Interest in a car is not consent to be marketed to. When in doubt, leave the
   flag as it is.
2. Turning a consent flag **off** is always allowed and never needs confirmation.
3. Never copy {", ".join(f"`{f}`" for f in SENSITIVE_PROFILE_FIELDS)} out of
   `account/profile.json` into any other file.
4. Never delete or rewrite entries in `account/audit_log.json`. Append only.

## Notification preferences are not consents

`profile.notifications` controls how we contact the customer about things they
already asked for (price drops on their own shortlist, appointment reminders).
Those flags are freely settable on request. `profile.consents` is separate and
governs marketing and data sharing. A customer asking for price-drop *emails*
has not consented to marketing email.
"""

    return {
        "financing.md": financing,
        "shortlist.md": shortlist,
        "booking.md": booking,
        "privacy.md": privacy,
    }


def as_dict() -> dict[str, Any]:
    """Machine-readable snapshot, for transcripts and debugging."""
    return {
        "apr_by_credit_band": APR_BY_CREDIT_BAND,
        "allowed_terms": list(ALLOWED_TERMS),
        "min_down_payment_pct": MIN_DOWN_PAYMENT_PCT,
        "challenged_min_down_payment_pct": CHALLENGED_MIN_DOWN_PAYMENT_PCT,
        "max_payment_to_income": MAX_PAYMENT_TO_INCOME,
        "max_ltv": MAX_LTV,
        "max_shortlist_entries": MAX_SHORTLIST_ENTRIES,
        "max_open_appointments": MAX_OPEN_APPOINTMENTS,
        "tco_years": TCO_YEARS,
    }
