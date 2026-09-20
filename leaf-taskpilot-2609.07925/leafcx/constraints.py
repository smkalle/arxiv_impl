"""Hard constraints, in one serialisable form.

The same dict drives three things that must never disagree: the English the
customer writes in the brief, the gold solution, and the hidden tests.
"""

from __future__ import annotations

from typing import Any

#: Field -> (comparison, English template).  Order fixes the sentence order in
#: the brief, so a given constraint set always reads the same way.
_SPEC: tuple[tuple[str, str], ...] = (
    ("budget_max", "priced at or under ${value:,.0f}"),
    ("body_styles", "a {value}"),
    ("min_seats", "at least {value} seats"),
    ("min_year", "a {value} model year or newer"),
    ("max_mileage", "no more than {value:,} miles on it"),
    ("exclude_fuel", "not {value}"),
    ("require_fuel", "{value} only"),
    ("max_accidents", "at most {value} reported accident(s)"),
    ("certified_only", "certified pre-owned"),
    ("locations", "at our {value} lot"),
    ("min_range_miles", "at least {value} miles of range"),
)


def matches(vehicle: dict[str, Any], constraints: dict[str, Any]) -> bool:
    """True when `vehicle` satisfies every hard constraint."""
    if "budget_max" in constraints and vehicle["price"] > float(constraints["budget_max"]):
        return False
    if "body_styles" in constraints and vehicle["body_style"] not in constraints["body_styles"]:
        return False
    if "min_seats" in constraints and vehicle["seats"] < int(constraints["min_seats"]):
        return False
    if "min_year" in constraints and vehicle["year"] < int(constraints["min_year"]):
        return False
    if "max_mileage" in constraints and vehicle["mileage"] > int(constraints["max_mileage"]):
        return False
    if "exclude_fuel" in constraints and vehicle["fuel"] in constraints["exclude_fuel"]:
        return False
    if "require_fuel" in constraints and vehicle["fuel"] not in constraints["require_fuel"]:
        return False
    if "max_accidents" in constraints and vehicle["accidents"] > int(constraints["max_accidents"]):
        return False
    if constraints.get("certified_only") and not vehicle["certified"]:
        return False
    if "locations" in constraints and vehicle["location"] not in constraints["locations"]:
        return False
    if "min_range_miles" in constraints and vehicle.get("range_miles", 10**6) < int(
        constraints["min_range_miles"]
    ):
        return False
    return True


def _render_value(field: str, value: Any) -> str:
    if isinstance(value, list):
        if len(value) == 1:
            return str(value[0])
        return " or ".join(str(v) for v in value[:-1]) + " or " + str(value[-1])
    return str(value)


def describe(constraints: dict[str, Any]) -> list[str]:
    """Constraints as English fragments, for the customer brief."""
    fragments: list[str] = []
    for field, template in _SPEC:
        if field not in constraints:
            continue
        value = constraints[field]
        if field == "certified_only":
            if value:
                fragments.append("certified pre-owned")
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            fragments.append(template.format(value=value))
        else:
            fragments.append(template.format(value=_render_value(field, value)))
    return fragments


def as_sentence(constraints: dict[str, Any]) -> str:
    fragments = describe(constraints)
    if not fragments:
        return "no hard requirements"
    if len(fragments) == 1:
        return fragments[0]
    return ", ".join(fragments[:-1]) + ", and " + fragments[-1]


def as_bullets(constraints: dict[str, Any]) -> str:
    return "\n".join(f"- {fragment}" for fragment in describe(constraints))
