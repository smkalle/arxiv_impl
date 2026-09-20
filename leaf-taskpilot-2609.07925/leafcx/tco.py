"""Five-year total cost of ownership, and the financing arithmetic.

Both are pure functions of a vehicle record, so `search_inventory`, the
`quote_finance` tool and the hidden tests all produce identical numbers.

Design note: the agent never has to compute TCO.  `search_inventory` hands it
`tco_5yr` per vehicle and the shortlist policy tells it to copy that value.
A 4B model is unreliable at multi-step arithmetic but perfectly capable of
sorting a list it was given, so the task tests planning and policy compliance
rather than mental math.
"""

from __future__ import annotations

from typing import Any

from . import policy

#: Model year treated as "now" for age calculations.
CURRENT_YEAR = 2026


def vehicle_age(vehicle: dict[str, Any], current_year: int = CURRENT_YEAR) -> int:
    return max(0, current_year - int(vehicle["year"]))


def depreciation_5yr(vehicle: dict[str, Any]) -> int:
    """Asking price minus projected resale value after five more years."""
    price = float(vehicle["price"])
    retention = policy.ANNUAL_RETENTION.get(vehicle["body_style"], 0.855)
    resale = price * (retention ** policy.TCO_YEARS)
    return int(round(price - resale))


def energy_cost_5yr(vehicle: dict[str, Any], annual_miles: int = policy.DEFAULT_ANNUAL_MILES) -> int:
    """Fuel for combustion vehicles, electricity for EVs."""
    miles = annual_miles * policy.TCO_YEARS
    if vehicle["fuel"] == "electric":
        efficiency = float(vehicle["miles_per_kwh"])
        return int(round(miles / efficiency * policy.ELECTRICITY_PRICE_PER_KWH))
    mpg = float(vehicle["mpg"])
    return int(round(miles / mpg * policy.FUEL_PRICE_PER_GALLON))


def insurance_5yr(vehicle: dict[str, Any]) -> int:
    flat = policy.INSURANCE_FLAT.get(vehicle["body_style"], 850)
    annual = flat + policy.INSURANCE_RATE_ON_PRICE * float(vehicle["price"])
    return int(round(annual * policy.TCO_YEARS))


def maintenance_5yr(vehicle: dict[str, Any], current_year: int = CURRENT_YEAR) -> int:
    base = policy.MAINTENANCE_BASE.get(vehicle["body_style"], 700)
    # reliability_score runs 1 (poor) to 5 (excellent); 3 is neutral.
    reliability = float(vehicle.get("reliability_score", 3))
    reliability_factor = 1.0 + (3.0 - reliability) * 0.12
    annual = base * reliability_factor
    if vehicle["fuel"] == "electric":
        annual *= policy.EV_MAINTENANCE_MULTIPLIER
    age = vehicle_age(vehicle, current_year)
    surcharge = policy.MAINTENANCE_AGE_SURCHARGE_PER_YEAR * max(0, age - 3)
    return int(round((annual + surcharge) * policy.TCO_YEARS))


def tco_breakdown(
    vehicle: dict[str, Any],
    annual_miles: int = policy.DEFAULT_ANNUAL_MILES,
    current_year: int = CURRENT_YEAR,
) -> dict[str, int]:
    """Component-wise five-year ownership cost. Financing interest is excluded.

    Interest belongs to the financing quote, not to ownership cost: two buyers
    of the same car with different down payments own an identically costly car.
    """
    parts = {
        "depreciation": depreciation_5yr(vehicle),
        "energy": energy_cost_5yr(vehicle, annual_miles),
        "insurance": insurance_5yr(vehicle),
        "maintenance": maintenance_5yr(vehicle, current_year),
    }
    parts["total"] = sum(parts.values())
    return parts


def tco_5yr(
    vehicle: dict[str, Any],
    annual_miles: int = policy.DEFAULT_ANNUAL_MILES,
    current_year: int = CURRENT_YEAR,
) -> int:
    return tco_breakdown(vehicle, annual_miles, current_year)["total"]


def monthly_payment(principal: float, apr_pct: float, term_months: int) -> float:
    """Standard amortising loan payment."""
    if term_months <= 0:
        raise ValueError("term_months must be positive")
    if principal <= 0:
        return 0.0
    r = apr_pct / 100.0 / 12.0
    if r == 0:
        return principal / term_months
    factor = (1 + r) ** term_months
    return principal * r * factor / (factor - 1)


def finance_quote(
    price: float,
    down_payment: float,
    term_months: int,
    credit_band: str,
    gross_monthly_income: float,
    trade_in_value: float = 0.0,
) -> dict[str, Any]:
    """Evaluate one (term, down payment) combination against financing policy.

    Returns the numbers plus an explicit list of violated rules.  An empty
    `violations` list is the only thing that may be reported as pre-qualified.
    """
    price = float(price)
    down_payment = float(down_payment)
    trade_in_value = float(trade_in_value)
    total_down = down_payment + trade_in_value
    principal = max(0.0, price - total_down)
    apr = policy.apr_for(credit_band)

    violations: list[str] = []
    if term_months not in policy.ALLOWED_TERMS:
        violations.append(
            f"term_not_allowed: {term_months} not in {list(policy.ALLOWED_TERMS)}"
        )
    required_pct = policy.min_down_payment_pct(credit_band)
    if price > 0 and total_down / price < required_pct - 1e-9:
        violations.append(
            f"down_payment_below_minimum: {total_down / price:.3f} < {required_pct:.2f}"
        )
    if price > 0 and principal / price > policy.MAX_LTV + 1e-9:
        violations.append(f"ltv_exceeded: {principal / price:.3f} > {policy.MAX_LTV}")

    payment = (
        monthly_payment(principal, apr, term_months)
        if term_months in policy.ALLOWED_TERMS
        else 0.0
    )
    payment = round(payment, 2)

    if gross_monthly_income > 0:
        ratio = payment / gross_monthly_income
        if ratio > policy.MAX_PAYMENT_TO_INCOME + 1e-9:
            violations.append(
                f"payment_to_income_exceeded: {ratio:.3f} > {policy.MAX_PAYMENT_TO_INCOME}"
            )
    else:
        violations.append("income_unknown")

    total_paid = round(payment * term_months, 2)
    return {
        "price": round(price, 2),
        "down_payment": round(down_payment, 2),
        "trade_in_value": round(trade_in_value, 2),
        "amount_financed": round(principal, 2),
        "apr": apr,
        "term_months": term_months,
        "monthly_payment": payment,
        "total_interest": round(max(0.0, total_paid - principal), 2),
        "payment_to_income": (
            round(payment / gross_monthly_income, 4) if gross_monthly_income > 0 else None
        ),
        "violations": violations,
        "status": "prequalified" if not violations else "referred",
    }


def best_finance_quote(
    price: float,
    down_payment: float,
    credit_band: str,
    gross_monthly_income: float,
    trade_in_value: float = 0.0,
) -> dict[str, Any]:
    """The shortest allowed term that still satisfies every policy rule.

    Shortest-passing-term is the customer-favourable choice: it minimises total
    interest among the options that pre-qualify.  If nothing passes, the longest
    term's quote is returned so the failure reasons are visible.
    """
    attempts = [
        finance_quote(price, down_payment, term, credit_band, gross_monthly_income, trade_in_value)
        for term in policy.ALLOWED_TERMS
    ]
    passing = [q for q in attempts if not q["violations"]]
    if passing:
        chosen = min(passing, key=lambda q: q["term_months"])
    else:
        chosen = attempts[-1]
    chosen = dict(chosen)
    chosen["considered_terms"] = [
        {"term_months": q["term_months"], "monthly_payment": q["monthly_payment"],
         "violations": q["violations"]}
        for q in attempts
    ]
    return chosen
