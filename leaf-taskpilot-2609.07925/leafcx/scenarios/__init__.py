"""The six account-management scenario families.

`shortlist_build` is the flagship; the other five exercise the rest of a
self-serve account surface (propagation, financing, trade-in, scheduling,
consent).  Each is a task *family*: `build(seed, hint_level)` draws one
reproducible instance from it.
"""

from __future__ import annotations

from .base import HINT_LEVELS, Scenario, TaskInstance
from .consent_prefs import ConsentPrefsScenario
from .finance_prequal import FinancePrequalScenario
from .profile_update import ProfileUpdateScenario
from .shortlist import ShortlistScenario
from .test_drive import TestDriveScenario
from .trade_in import TradeInScenario

#: Registry, in the order the CLI lists them.
SCENARIOS: dict[str, Scenario] = {
    scenario.family: scenario
    for scenario in (
        ShortlistScenario(),
        ProfileUpdateScenario(),
        FinancePrequalScenario(),
        TradeInScenario(),
        TestDriveScenario(),
        ConsentPrefsScenario(),
    )
}

FAMILIES: tuple[str, ...] = tuple(SCENARIOS)


def get(family: str) -> Scenario:
    if family not in SCENARIOS:
        raise KeyError(f"unknown scenario family {family!r}; known: {', '.join(FAMILIES)}")
    return SCENARIOS[family]


def build(family: str, seed: int, hint_level: int = 0) -> TaskInstance:
    return get(family).build(seed, hint_level)


__all__ = [
    "FAMILIES",
    "HINT_LEVELS",
    "SCENARIOS",
    "Scenario",
    "TaskInstance",
    "build",
    "get",
]
