"""Deterministic used-car inventory generator.

No download, no dataset file, no network: a seed produces the same lot every
time, on a laptop and on a phone.  That matters for two reasons.  Hidden tests
have to be reproducible, and TaskPilot's solve-rate estimate is only meaningful
if the task is identical across rollouts.
"""

from __future__ import annotations

import hashlib
import random
from typing import Any, Iterable

from . import tco

#: (make, model, body_style, fuel, msrp_new, efficiency, reliability, seats, drivetrain)
#: `efficiency` is combined MPG, or miles per kWh for electric vehicles.
CATALOG: tuple[tuple[str, str, str, str, int, float, float, int, str], ...] = (
    ("Toyota", "Corolla", "sedan", "gas", 23500, 35.0, 4.6, 5, "fwd"),
    ("Toyota", "Camry", "sedan", "gas", 29500, 32.0, 4.6, 5, "fwd"),
    ("Toyota", "RAV4", "suv", "hybrid", 33500, 39.0, 4.5, 5, "awd"),
    ("Toyota", "Tacoma", "truck", "gas", 36500, 21.0, 4.4, 5, "4wd"),
    ("Honda", "Civic", "sedan", "gas", 25500, 36.0, 4.5, 5, "fwd"),
    ("Honda", "Accord", "sedan", "hybrid", 32500, 44.0, 4.4, 5, "fwd"),
    ("Honda", "CR-V", "suv", "gas", 31500, 30.0, 4.4, 5, "awd"),
    ("Honda", "Odyssey", "minivan", "gas", 39500, 22.0, 4.0, 8, "fwd"),
    ("Mazda", "Mazda3", "hatchback", "gas", 24500, 33.0, 4.3, 5, "fwd"),
    ("Mazda", "CX-5", "suv", "gas", 30500, 28.0, 4.2, 5, "awd"),
    ("Subaru", "Outback", "wagon", "gas", 31500, 28.0, 4.0, 5, "awd"),
    ("Subaru", "Forester", "suv", "gas", 29500, 29.0, 4.1, 5, "awd"),
    ("Hyundai", "Elantra", "sedan", "gas", 22500, 36.0, 3.9, 5, "fwd"),
    ("Hyundai", "Tucson", "suv", "hybrid", 32500, 37.0, 3.8, 5, "awd"),
    ("Hyundai", "Ioniq 5", "suv", "electric", 43500, 3.3, 3.7, 5, "awd"),
    ("Kia", "Forte", "sedan", "gas", 21500, 34.0, 3.8, 5, "fwd"),
    ("Kia", "Telluride", "suv", "gas", 40500, 23.0, 3.9, 8, "awd"),
    ("Kia", "Niro", "hatchback", "hybrid", 27500, 48.0, 3.9, 5, "fwd"),
    ("Nissan", "Sentra", "sedan", "gas", 21500, 33.0, 3.4, 5, "fwd"),
    ("Nissan", "Rogue", "suv", "gas", 29500, 30.0, 3.3, 5, "awd"),
    ("Nissan", "Leaf", "hatchback", "electric", 29500, 3.6, 3.4, 5, "fwd"),
    ("Ford", "Escape", "suv", "hybrid", 31500, 37.0, 3.2, 5, "awd"),
    ("Ford", "F-150", "truck", "gas", 44500, 19.0, 3.3, 5, "4wd"),
    ("Ford", "Mustang", "coupe", "gas", 34500, 22.0, 3.2, 4, "rwd"),
    ("Chevrolet", "Malibu", "sedan", "gas", 26500, 31.0, 3.1, 5, "fwd"),
    ("Chevrolet", "Equinox", "suv", "gas", 28500, 28.0, 3.0, 5, "awd"),
    ("Chevrolet", "Bolt EUV", "hatchback", "electric", 30500, 3.9, 3.2, 5, "fwd"),
    ("Volkswagen", "Jetta", "sedan", "gas", 24500, 35.0, 3.3, 5, "fwd"),
    ("Volkswagen", "Tiguan", "suv", "gas", 30500, 27.0, 3.1, 7, "awd"),
    ("Tesla", "Model 3", "sedan", "electric", 42500, 4.0, 3.5, 5, "rwd"),
)

LOCATIONS: tuple[str, ...] = (
    "Fremont",
    "San Jose",
    "Oakland",
    "Concord",
    "Santa Clara",
)

COLORS: tuple[str, ...] = ("white", "black", "silver", "grey", "blue", "red", "green")

#: Model years that can appear on the lot.
YEARS: tuple[int, ...] = (2018, 2019, 2020, 2021, 2022, 2023, 2024)

#: Depreciation used to price a car *up to today*, distinct from the forward
#: retention curve in `policy.ANNUAL_RETENTION` used for resale projection.
_PRICING_RETENTION = 0.84


def _vin(seed_material: str) -> str:
    """A syntactically plausible 17-character VIN, derived deterministically."""
    alphabet = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"  # no I, O, Q — as in real VINs
    digest = hashlib.sha256(seed_material.encode()).hexdigest()
    return "".join(alphabet[int(digest[i : i + 2], 16) % len(alphabet)] for i in range(0, 34, 2))


def _price(rng: random.Random, msrp: int, age: int, mileage: int, accidents: int, certified: bool) -> int:
    value = msrp * (_PRICING_RETENTION ** age)
    expected_miles = max(1, age) * 12000
    mileage_delta = (mileage - expected_miles) / 10000.0
    value *= 1.0 - 0.035 * mileage_delta
    value *= 1.0 - 0.06 * accidents
    if certified:
        value *= 1.05
    value *= rng.uniform(0.94, 1.06)
    return int(round(max(3500.0, value) / 50.0) * 50)


def generate_inventory(seed: int = 20260920, count: int = 300) -> list[dict[str, Any]]:
    """Build `count` vehicles. Same seed and count always give the same lot."""
    rng = random.Random(seed)
    vehicles: list[dict[str, Any]] = []
    for i in range(count):
        make, model, body, fuel, msrp, efficiency, reliability, seats, drivetrain = rng.choice(CATALOG)
        year = rng.choice(YEARS)
        age = max(0, tco.CURRENT_YEAR - year)
        mileage = max(1200, int(rng.gauss(age * 12000, 4500)))
        mileage = int(round(mileage / 100) * 100)
        accidents = 0 if rng.random() < 0.78 else rng.choice([1, 1, 2])
        certified = rng.random() < 0.30 and age <= 5 and accidents == 0
        vehicle: dict[str, Any] = {
            "vin": _vin(f"{seed}:{i}:{make}:{model}:{year}"),
            "year": year,
            "make": make,
            "model": model,
            "body_style": body,
            "fuel": fuel,
            "drivetrain": drivetrain,
            "transmission": "manual" if body == "coupe" and rng.random() < 0.25 else "automatic",
            "seats": seats,
            "mileage": mileage,
            "accidents": accidents,
            "owners": 1 + int(rng.random() * 2.4),
            "certified": certified,
            "color": rng.choice(COLORS),
            "location": rng.choice(LOCATIONS),
            "days_on_lot": rng.randint(1, 140),
            "reliability_score": round(reliability + rng.uniform(-0.25, 0.25), 2),
        }
        if fuel == "electric":
            vehicle["miles_per_kwh"] = efficiency
            vehicle["range_miles"] = int(round(efficiency * rng.uniform(62, 82)))
        else:
            vehicle["mpg"] = efficiency
        vehicle["price"] = _price(rng, msrp, age, mileage, accidents, certified)
        vehicles.append(vehicle)

    # VINs are hashed from the catalog entry, so the same model/year drawn twice
    # collides.  De-duplicate by salting until unique — still deterministic.
    seen: set[str] = set()
    for idx, vehicle in enumerate(vehicles):
        salt = 0
        while vehicle["vin"] in seen:
            salt += 1
            vehicle["vin"] = _vin(f"{seed}:{idx}:{vehicle['make']}:{vehicle['model']}:{vehicle['year']}:{salt}")
        seen.add(vehicle["vin"])
    vehicles.sort(key=lambda v: v["vin"])
    return vehicles


def enrich(vehicles: Iterable[dict[str, Any]], annual_miles: int) -> list[dict[str, Any]]:
    """Attach `tco_5yr` (and its breakdown) to each vehicle."""
    out = []
    for vehicle in vehicles:
        record = dict(vehicle)
        breakdown = tco.tco_breakdown(vehicle, annual_miles=annual_miles)
        record["tco_5yr"] = breakdown["total"]
        record["tco_breakdown"] = {k: v for k, v in breakdown.items() if k != "total"}
        out.append(record)
    return out
