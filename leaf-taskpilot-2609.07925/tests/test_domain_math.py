"""TCO and financing arithmetic, plus inventory determinism."""

from __future__ import annotations

import pytest

from leafcx import inventory, policy, tco


def _vehicle(**overrides):
    base = {
        "year": 2022,
        "price": 24000,
        "body_style": "sedan",
        "fuel": "gas",
        "mpg": 32.0,
        "reliability_score": 3.0,
        "mileage": 48000,
    }
    base.update(overrides)
    return base


def test_tco_components_sum_to_the_total() -> None:
    breakdown = tco.tco_breakdown(_vehicle())
    assert breakdown["total"] == sum(v for k, v in breakdown.items() if k != "total")


def test_more_miles_costs_more() -> None:
    assert tco.tco_5yr(_vehicle(), annual_miles=25000) > tco.tco_5yr(_vehicle(), annual_miles=8000)


def test_electric_skips_fuel_and_most_maintenance() -> None:
    gas = _vehicle()
    ev = _vehicle(fuel="electric", miles_per_kwh=3.6)
    ev.pop("mpg")
    assert tco.energy_cost_5yr(ev) < tco.energy_cost_5yr(gas)
    assert tco.maintenance_5yr(ev) < tco.maintenance_5yr(gas)


def test_poor_reliability_costs_more_to_maintain() -> None:
    assert tco.maintenance_5yr(_vehicle(reliability_score=2.0)) > tco.maintenance_5yr(
        _vehicle(reliability_score=4.5)
    )


def test_monthly_payment_matches_the_amortisation_formula() -> None:
    # 12,000 over 48 months at 8.4% APR.
    payment = tco.monthly_payment(12000, 8.4, 48)
    assert payment == pytest.approx(295.22, abs=0.02)
    assert tco.monthly_payment(12000, 0.0, 48) == pytest.approx(250.0)
    assert tco.monthly_payment(0, 8.4, 48) == 0.0


def test_quote_flags_a_disallowed_term_and_a_thin_deposit() -> None:
    quote = tco.finance_quote(
        price=30000,
        down_payment=500,
        term_months=84,
        credit_band="challenged",
        gross_monthly_income=2000,
    )
    assert quote["status"] == "referred"
    kinds = {v.split(":")[0] for v in quote["violations"]}
    assert {"term_not_allowed", "down_payment_below_minimum"} <= kinds
    # A term outside the allowed set has no payment to test against income, so
    # that rule is not evaluated; the disallowed term already refers the quote.
    assert "payment_to_income_exceeded" not in kinds
    assert quote["monthly_payment"] == 0.0


def test_quote_flags_payment_to_income() -> None:
    quote = tco.finance_quote(
        price=30000,
        down_payment=6000,
        term_months=60,
        credit_band="fair",
        gross_monthly_income=2000,
    )
    assert quote["status"] == "referred"
    assert any(v.startswith("payment_to_income_exceeded") for v in quote["violations"])


def test_unknown_income_is_itself_a_violation() -> None:
    quote = tco.finance_quote(
        price=10000, down_payment=3000, term_months=36, credit_band="good", gross_monthly_income=0
    )
    assert "income_unknown" in quote["violations"]


def test_best_quote_picks_the_shortest_passing_term() -> None:
    quote = tco.best_finance_quote(
        price=18000, down_payment=4000, credit_band="excellent", gross_monthly_income=9000
    )
    assert quote["status"] == "prequalified"
    passing = [
        attempt["term_months"] for attempt in quote["considered_terms"] if not attempt["violations"]
    ]
    assert quote["term_months"] == min(passing)


def test_best_quote_returns_reasons_when_nothing_passes() -> None:
    quote = tco.best_finance_quote(
        price=30000, down_payment=100, credit_band="challenged", gross_monthly_income=1500
    )
    assert quote["status"] == "referred"
    assert quote["violations"]


def test_challenged_band_needs_a_bigger_deposit() -> None:
    assert policy.min_down_payment_pct("challenged") > policy.min_down_payment_pct("good")


def test_unknown_credit_band_falls_back_to_the_worst_tier() -> None:
    assert policy.apr_for("nonsense") == policy.APR_BY_CREDIT_BAND["challenged"]


def test_inventory_is_deterministic_and_unique() -> None:
    first = inventory.generate_inventory(seed=7, count=200)
    second = inventory.generate_inventory(seed=7, count=200)
    assert first == second
    assert len({v["vin"] for v in first}) == 200
    assert all(len(v["vin"]) == 17 for v in first)


def test_a_different_seed_gives_a_different_lot() -> None:
    a = inventory.generate_inventory(seed=7, count=100)
    b = inventory.generate_inventory(seed=8, count=100)
    assert [v["vin"] for v in a] != [v["vin"] for v in b]


def test_every_vehicle_can_be_costed() -> None:
    for vehicle in inventory.generate_inventory(seed=11, count=120):
        assert tco.tco_5yr(vehicle) > 0


def test_policy_pages_document_every_number_the_grader_uses() -> None:
    pages = policy.policy_pages()
    financing = pages["financing.md"]
    for band, apr in policy.APR_BY_CREDIT_BAND.items():
        assert band in financing and f"{apr:.1f}%" in financing
    for term in policy.ALLOWED_TERMS:
        assert str(term) in financing
    assert str(policy.MAX_SHORTLIST_ENTRIES) in pages["shortlist.md"]
    assert str(policy.MAX_OPEN_APPOINTMENTS) in pages["booking.md"]
