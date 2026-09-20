"""Domain tools layered on top of Leaf's five.

The paper's finding is that the generic harness carried most of the pre-RL gain,
so these three are kept thin and non-magical: they surface facts the agent would
otherwise have to compute (inventory filtering, loan arithmetic) and give it a
way to check its own work.  None of them decide anything — the agent still has
to choose, rank, justify and write the account files itself.
"""

from __future__ import annotations

import json
from typing import Any

from .. import account, policy, sandbox, tco

#: Columns shown by `search_inventory`, in order.
_COLUMNS = (
    "vin",
    "year",
    "make",
    "model",
    "body_style",
    "fuel",
    "drivetrain",
    "seats",
    "mileage",
    "price",
    "tco_5yr",
    "location",
    "certified",
    "accidents",
)

MAX_SEARCH_RESULTS = 25
DEFAULT_SEARCH_RESULTS = 10

_SORT_KEYS = {
    "tco_5yr": lambda v: (v["tco_5yr"], v["price"], v["mileage"]),
    "price": lambda v: (v["price"], v["tco_5yr"], v["mileage"]),
    "mileage": lambda v: (v["mileage"], v["price"]),
    "year": lambda v: (-v["year"], v["price"]),
}


def search_inventory(
    make: str | None = None,
    model: str | None = None,
    body_style: str | None = None,
    fuel: str | None = None,
    drivetrain: str | None = None,
    max_price: float | None = None,
    min_price: float | None = None,
    min_year: int | None = None,
    max_mileage: int | None = None,
    min_seats: int | None = None,
    max_accidents: int | None = None,
    certified_only: bool = False,
    location: str | None = None,
    min_range_miles: int | None = None,
    sort_by: str = "tco_5yr",
    limit: int = DEFAULT_SEARCH_RESULTS,
) -> str:
    """Filter the lot and return matching vehicles with five-year TCO attached."""
    root = sandbox.workspace_root()
    try:
        vehicles = account.load_inventory(root)
    except account.AccountError as exc:
        return f"error: {exc}"

    profile = account.load_json("account/profile.json", root, default={})
    annual_miles = int(profile.get("annual_miles") or policy.DEFAULT_ANNUAL_MILES)

    def matches(v: dict[str, Any]) -> bool:
        if make and v["make"].lower() != str(make).lower():
            return False
        if model and str(model).lower() not in v["model"].lower():
            return False
        if body_style and v["body_style"].lower() != str(body_style).lower():
            return False
        if fuel and v["fuel"].lower() != str(fuel).lower():
            return False
        if drivetrain and v["drivetrain"].lower() != str(drivetrain).lower():
            return False
        if max_price is not None and v["price"] > float(max_price):
            return False
        if min_price is not None and v["price"] < float(min_price):
            return False
        if min_year is not None and v["year"] < int(min_year):
            return False
        if max_mileage is not None and v["mileage"] > int(max_mileage):
            return False
        if min_seats is not None and v["seats"] < int(min_seats):
            return False
        if max_accidents is not None and v["accidents"] > int(max_accidents):
            return False
        if certified_only and not v["certified"]:
            return False
        if location and v["location"].lower() != str(location).lower():
            return False
        if min_range_miles is not None and v.get("range_miles", 10**6) < int(min_range_miles):
            return False
        return True

    hits = [v for v in vehicles if matches(v)]
    enriched = _attach_tco(hits, annual_miles)
    key = _SORT_KEYS.get(str(sort_by), _SORT_KEYS["tco_5yr"])
    enriched.sort(key=key)

    limit = max(1, min(int(limit or DEFAULT_SEARCH_RESULTS), MAX_SEARCH_RESULTS))
    shown = enriched[:limit]
    if not shown:
        return "0 vehicles match. Relax a filter and search again."

    header = " | ".join(_COLUMNS)
    rows = [" | ".join(_cell(v, column) for column in _COLUMNS) for v in shown]
    footer = f"showing {len(shown)} of {len(enriched)} matches, sorted by {sort_by}"
    note = (
        "tco_5yr is the five-year total cost of ownership "
        "(depreciation + energy + insurance + maintenance) at "
        f"{annual_miles} miles/year. Copy it verbatim into the shortlist."
    )
    return "\n".join([header, "-" * len(header), *rows, "", footer, note])


def _attach_tco(vehicles: list[dict[str, Any]], annual_miles: int) -> list[dict[str, Any]]:
    out = []
    for vehicle in vehicles:
        record = dict(vehicle)
        record["tco_5yr"] = tco.tco_5yr(vehicle, annual_miles=annual_miles)
        out.append(record)
    return out


def _cell(vehicle: dict[str, Any], column: str) -> str:
    value = vehicle.get(column, "")
    if isinstance(value, bool):
        return "yes" if value else "no"
    return str(value)


def quote_finance(
    vin: str,
    down_payment: float,
    term_months: int | None = None,
    include_trade_in: bool = True,
) -> str:
    """Price a loan for one vehicle against the financing policy.

    Credit band, gross monthly income and any recorded trade-in value are read
    from the account, so the agent does not have to restate them.  Omit
    `term_months` to get the shortest allowed term that satisfies every rule.
    """
    root = sandbox.workspace_root()
    try:
        by_vin = account.inventory_by_vin(root)
    except account.AccountError as exc:
        return f"error: {exc}"
    if vin not in by_vin:
        return f"error: VIN {vin} is not in the inventory"

    profile = account.load_json("account/profile.json", root, default={})
    credit_band = profile.get("credit_band", "fair")
    income = float(profile.get("gross_monthly_income") or 0)

    trade_in_value = 0.0
    if include_trade_in:
        trade_in = account.load_json("account/trade_in.json", root, default={})
        if str(trade_in.get("status", "")).lower() in {"accepted", "valued", "applied"}:
            trade_in_value = float(trade_in.get("offer_value") or 0)

    price = float(by_vin[vin]["price"])
    if term_months is None:
        quote = tco.best_finance_quote(price, down_payment, credit_band, income, trade_in_value)
    else:
        quote = tco.finance_quote(
            price, down_payment, int(term_months), credit_band, income, trade_in_value
        )
    quote["vin"] = vin
    quote["credit_band"] = credit_band
    quote["gross_monthly_income"] = income
    return json.dumps(quote, indent=2)


def validate_account() -> str:
    """Check the account against the written policies. Run this before you stop.

    Reports structural and policy problems.  It does not know the customer's
    request, so a clean result means "nothing provably wrong", not "done".
    """
    problems = account.validate(sandbox.workspace_root())
    if not problems:
        return "ok: no policy or schema problems found"
    lines = [f"{len(problems)} problem(s) found:"]
    lines += [f"  {i + 1}. {p}" for i, p in enumerate(problems)]
    return "\n".join(lines)


DOMAIN_TOOLS = {
    "search_inventory": search_inventory,
    "quote_finance": quote_finance,
    "validate_account": validate_account,
}

DOMAIN_TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_inventory",
            "description": (
                "Search the used-car lot. Every filter is optional and they combine with AND. "
                "Results include tco_5yr, the five-year total cost of ownership."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "make": {"type": "string"},
                    "model": {"type": "string", "description": "Substring match."},
                    "body_style": {
                        "type": "string",
                        "enum": ["sedan", "hatchback", "suv", "truck", "minivan", "coupe", "wagon"],
                    },
                    "fuel": {"type": "string", "enum": ["gas", "hybrid", "electric", "diesel"]},
                    "drivetrain": {"type": "string", "enum": ["fwd", "rwd", "awd", "4wd"]},
                    "max_price": {"type": "number"},
                    "min_price": {"type": "number"},
                    "min_year": {"type": "integer"},
                    "max_mileage": {"type": "integer"},
                    "min_seats": {"type": "integer"},
                    "max_accidents": {"type": "integer"},
                    "certified_only": {"type": "boolean"},
                    "location": {"type": "string"},
                    "min_range_miles": {"type": "integer", "description": "Electric vehicles only."},
                    "sort_by": {"type": "string", "enum": ["tco_5yr", "price", "mileage", "year"]},
                    "limit": {"type": "integer", "description": f"1-{MAX_SEARCH_RESULTS}."},
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "quote_finance",
            "description": (
                "Price a loan for one VIN using the customer's credit band, income and "
                "trade-in. Omit term_months to get the shortest term that passes every policy rule."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "vin": {"type": "string"},
                    "down_payment": {"type": "number"},
                    "term_months": {"type": "integer", "enum": list(policy.ALLOWED_TERMS)},
                    "include_trade_in": {"type": "boolean"},
                },
                "required": ["vin", "down_payment"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "validate_account",
            "description": (
                "Check the account files against the written policies. "
                "Call this before you finish, and fix anything it reports."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
]
