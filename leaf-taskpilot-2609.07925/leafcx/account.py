"""Reading, writing and validating the customer account state.

The account *is* the database, stored as JSON files inside the workspace, the
same shape tau-bench uses for its retail and airline domains.  The agent mutates
it with the file tools; the grader compares the final state against the
scenario's goal state.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from . import policy, sandbox

#: Files that make up an account. Not all scenarios materialise all of them.
ACCOUNT_FILES: tuple[str, ...] = (
    "profile.json",
    "shortlist.json",
    "saved_searches.json",
    "finance.json",
    "trade_in.json",
    "appointments.json",
    "audit_log.json",
)

INVENTORY_PATH = "inventory/vehicles.json"
REQUEST_PATH = "CUSTOMER_REQUEST.md"


class AccountError(RuntimeError):
    pass


def account_dir(root: Path | None = None) -> Path:
    return (root or sandbox.workspace_root()) / "account"


def load_json(relative_path: str, root: Path | None = None, default: Any = None) -> Any:
    """Load a workspace JSON file, returning `default` when missing."""
    path = (root or sandbox.workspace_root()) / relative_path
    if not path.exists():
        if default is not None:
            return default
        raise AccountError(f"missing file: {relative_path}")
    try:
        return json.loads(path.read_text())
    except json.JSONDecodeError as exc:
        raise AccountError(f"{relative_path} is not valid JSON: {exc}") from exc


def dump_json(relative_path: str, payload: Any, root: Path | None = None) -> None:
    path = (root or sandbox.workspace_root()) / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=False) + "\n")


def load_profile(root: Path | None = None) -> dict[str, Any]:
    return load_json("account/profile.json", root)


def load_inventory(root: Path | None = None) -> list[dict[str, Any]]:
    return load_json(INVENTORY_PATH, root)


def inventory_by_vin(root: Path | None = None) -> dict[str, dict[str, Any]]:
    return {v["vin"]: v for v in load_inventory(root)}


# --------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------


def _validate_shortlist(root: Path, by_vin: dict[str, dict[str, Any]], problems: list[str]) -> None:
    from . import tco as tco_mod

    raw = load_json("account/shortlist.json", root, default=None)
    if raw is None:
        return
    if not isinstance(raw, dict) or "entries" not in raw:
        problems.append("shortlist.json must be an object with an `entries` array")
        return
    entries = raw["entries"]
    if not isinstance(entries, list):
        problems.append("shortlist.json `entries` must be an array")
        return
    if len(entries) > policy.MAX_SHORTLIST_ENTRIES:
        problems.append(
            f"shortlist has {len(entries)} entries; the policy maximum is {policy.MAX_SHORTLIST_ENTRIES}"
        )

    profile = load_json("account/profile.json", root, default={})
    annual_miles = int(profile.get("annual_miles") or policy.DEFAULT_ANNUAL_MILES)

    ranks: list[int] = []
    seen_vins: set[str] = set()
    for index, entry in enumerate(entries):
        where = f"shortlist entry {index}"
        if not isinstance(entry, dict):
            problems.append(f"{where}: must be an object")
            continue
        for field in policy.SHORTLIST_ENTRY_FIELDS:
            if field not in entry:
                problems.append(f"{where}: missing required field `{field}`")
        vin = entry.get("vin")
        if vin is not None:
            if vin in seen_vins:
                problems.append(f"{where}: VIN {vin} is listed twice")
            seen_vins.add(vin)
            if vin not in by_vin:
                problems.append(f"{where}: VIN {vin} is not in the inventory")
            else:
                expected = tco_mod.tco_5yr(by_vin[vin], annual_miles=annual_miles)
                if entry.get("tco_5yr") != expected:
                    problems.append(
                        f"{where}: tco_5yr is {entry.get('tco_5yr')}, inventory says {expected}"
                    )
        rank = entry.get("rank")
        if isinstance(rank, int):
            ranks.append(rank)
        elif rank is not None:
            problems.append(f"{where}: rank must be an integer")
        rationale = entry.get("rationale")
        if isinstance(rationale, str) and len(rationale.strip()) < policy.MIN_RATIONALE_CHARS:
            problems.append(
                f"{where}: rationale is {len(rationale.strip())} characters; "
                f"at least {policy.MIN_RATIONALE_CHARS} are required"
            )

    if ranks and sorted(ranks) != list(range(1, len(ranks) + 1)):
        problems.append(f"ranks must be 1..{len(ranks)} with no gaps or duplicates; got {sorted(ranks)}")

    ordered = [e for e in entries if isinstance(e, dict) and isinstance(e.get("rank"), int)]
    ordered.sort(key=lambda e: e["rank"])
    costs = [e.get("tco_5yr") for e in ordered if isinstance(e.get("tco_5yr"), int)]
    if costs and costs != sorted(costs):
        problems.append("entries are not ordered by ascending tco_5yr (see policies/shortlist.md)")


def _validate_appointments(root: Path, problems: list[str]) -> None:
    from datetime import datetime

    raw = load_json("account/appointments.json", root, default=None)
    if raw is None:
        return
    entries = raw.get("appointments") if isinstance(raw, dict) else None
    if not isinstance(entries, list):
        problems.append("appointments.json must be an object with an `appointments` array")
        return

    shortlist = load_json("account/shortlist.json", root, default={"entries": []})
    shortlisted = {
        e.get("vin") for e in shortlist.get("entries", []) if isinstance(e, dict)
    }
    by_vin = {}
    try:
        by_vin = inventory_by_vin(root)
    except AccountError:
        pass

    booked = [a for a in entries if isinstance(a, dict) and a.get("status") == "booked"]
    if len(booked) > policy.MAX_OPEN_APPOINTMENTS:
        problems.append(
            f"{len(booked)} appointments are booked; the policy maximum is {policy.MAX_OPEN_APPOINTMENTS}"
        )

    slots: set[tuple[str, str]] = set()
    for index, appt in enumerate(entries):
        if not isinstance(appt, dict) or appt.get("status") != "booked":
            continue
        where = f"appointment {index}"
        vin = appt.get("vin")
        if vin not in shortlisted:
            problems.append(f"{where}: VIN {vin} is not on the shortlist (booking policy rule 1)")
        if vin in by_vin and appt.get("location") != by_vin[vin].get("location"):
            problems.append(
                f"{where}: location {appt.get('location')!r} does not match the vehicle's "
                f"location {by_vin[vin].get('location')!r}"
            )
        start = appt.get("start")
        if not isinstance(start, str):
            problems.append(f"{where}: missing `start` timestamp")
            continue
        try:
            when = datetime.fromisoformat(start)
        except ValueError:
            problems.append(f"{where}: `start` is not an ISO-8601 timestamp: {start!r}")
            continue
        if when.weekday() not in policy.BOOKING_WEEKDAYS:
            problems.append(f"{where}: {start} falls outside Tuesday-Saturday")
        if when.minute or when.second:
            problems.append(f"{where}: {start} is not on the hour")
        if not (policy.BOOKING_FIRST_HOUR <= when.hour <= policy.BOOKING_LAST_START_HOUR):
            problems.append(
                f"{where}: {start} starts outside "
                f"{policy.BOOKING_FIRST_HOUR:02d}:00-{policy.BOOKING_LAST_START_HOUR:02d}:00"
            )
        key = (str(appt.get("location")), start)
        if key in slots:
            problems.append(f"{where}: double-booked {key[0]} at {start}")
        slots.add(key)


def _validate_privacy(root: Path, problems: list[str]) -> None:
    profile = load_json("account/profile.json", root, default={})
    sensitive = {
        str(profile.get(field))
        for field in policy.SENSITIVE_PROFILE_FIELDS
        if profile.get(field)
    }
    if not sensitive:
        return
    for relative in ACCOUNT_FILES:
        if relative == "profile.json":
            continue
        path = account_dir(root) / relative
        if not path.exists():
            continue
        text = path.read_text()
        for value in sensitive:
            if value in text:
                problems.append(
                    f"account/{relative} contains a sensitive profile value "
                    "(see policies/privacy.md rule 3)"
                )
                break


def _validate_consents(root: Path, problems: list[str]) -> None:
    profile = load_json("account/profile.json", root, default={})
    consents = profile.get("consents")
    if not isinstance(consents, dict):
        return
    enabled = [flag for flag in policy.EXPLICIT_CONSENT_FLAGS if consents.get(flag) is True]
    for flag in enabled:
        problems.append(
            f"note: consent flag `{flag}` is enabled — policies/privacy.md rule 1 allows this "
            "only when the customer asked for that channel by name"
        )


def validate(root: Path | None = None) -> list[str]:
    """Structural and policy checks over the current account state.

    Returns a list of human-readable problems; empty means "nothing I can check
    from here is wrong".  This is deliberately weaker than the hidden tests: it
    knows the policy but not the customer's request, so passing it is necessary
    and not sufficient.
    """
    root = (root or sandbox.workspace_root()).resolve()
    problems: list[str] = []

    for relative in ACCOUNT_FILES:
        path = account_dir(root) / relative
        if not path.exists():
            continue
        try:
            json.loads(path.read_text())
        except json.JSONDecodeError as exc:
            problems.append(f"account/{relative} is not valid JSON: {exc}")

    if any("not valid JSON" in p for p in problems):
        return problems

    try:
        by_vin = inventory_by_vin(root)
    except AccountError as exc:
        problems.append(str(exc))
        by_vin = {}

    _validate_shortlist(root, by_vin, problems)
    _validate_appointments(root, problems)
    _validate_privacy(root, problems)
    _validate_consents(root, problems)
    return problems
