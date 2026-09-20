from __future__ import annotations

import json
from pathlib import Path

from leafcx import grader, scenarios
from leafcx.tools import domain, files


def test_read_numbers_lines_and_reports_the_tail(workspace: Path) -> None:
    (workspace / "notes.txt").write_text("\n".join(f"line {i}" for i in range(1, 11)))
    out = files.read("notes.txt", offset=1, limit=3)
    assert "    1|line 1" in out
    assert "7 more line(s)" in out


def test_read_missing_file_is_an_error_not_an_exception(workspace: Path) -> None:
    assert files.read("nope.txt").startswith("error: no such file")


def test_edit_requires_a_unique_span(workspace: Path) -> None:
    target = workspace / "f.txt"
    target.write_text("alpha\nbeta\nalpha\n")
    assert files.edit("f.txt", "alpha", "gamma").startswith("edit failed")
    assert target.read_text() == "alpha\nbeta\nalpha\n"

    assert files.edit("f.txt", "beta", "gamma") == "edited f.txt"
    assert target.read_text() == "alpha\ngamma\nalpha\n"

    assert files.edit("f.txt", "missing", "x").startswith("edit failed")


def test_glob_skips_git_and_pycache(workspace: Path) -> None:
    (workspace / "account").mkdir()
    (workspace / "account" / "profile.json").write_text("{}")
    (workspace / ".git").mkdir()
    (workspace / ".git" / "config").write_text("x")
    assert files.glob("*.json") == "account/profile.json"


def test_bash_runs_in_the_workspace(workspace: Path) -> None:
    (workspace / "hello.txt").write_text("hi")
    out = files.bash("ls")
    assert "exit=0" in out and "hello.txt" in out


def test_bash_timeout_is_reported(workspace: Path) -> None:
    out = files.bash("sleep 5", timeout=1)
    assert out.startswith("exit=timeout")


def _materialized(workspace: Path, isolated_paths: Path, family: str = "shortlist_build"):
    task = scenarios.build(family, 3)
    grader.materialize(task, workspace, isolated_paths / "hidden_tests")
    return task


def test_search_inventory_filters_and_reports_tco(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths)
    out = domain.search_inventory(max_price=12000, body_style="sedan", limit=5)
    assert "tco_5yr" in out
    inventory = json.loads((workspace / "inventory" / "vehicles.json").read_text())
    by_vin = {v["vin"]: v for v in inventory}
    for line in out.splitlines():
        vin = line.split(" | ")[0]
        if vin in by_vin:
            assert by_vin[vin]["price"] <= 12000
            assert by_vin[vin]["body_style"] == "sedan"


def test_search_inventory_reports_no_matches_helpfully(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths)
    assert domain.search_inventory(max_price=1).startswith("0 vehicles match")


def test_quote_finance_uses_the_profile(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths, "finance_prequal")
    inventory = json.loads((workspace / "inventory" / "vehicles.json").read_text())
    vin = inventory[0]["vin"]
    quote = json.loads(domain.quote_finance(vin=vin, down_payment=2000))
    profile = json.loads((workspace / "account" / "profile.json").read_text())
    assert quote["credit_band"] == profile["credit_band"]
    assert quote["status"] in {"prequalified", "referred"}
    assert quote["vin"] == vin


def test_quote_finance_rejects_unknown_vin(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths, "finance_prequal")
    assert domain.quote_finance(vin="NOPE", down_payment=1000).startswith("error:")


def test_validate_account_is_clean_on_a_fresh_workspace(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths)
    assert domain.validate_account().startswith("ok:")


def test_validate_account_catches_a_bad_shortlist(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths)
    (workspace / "account" / "shortlist.json").write_text(
        json.dumps(
            {
                "updated_by": "agent",
                "entries": [
                    {"rank": 1, "vin": "NOT-A-VIN", "tco_5yr": 1, "rationale": "short"},
                    {"rank": 3, "vin": "ALSO-NOT", "tco_5yr": 2, "rationale": "also short"},
                ],
            }
        )
    )
    report = domain.validate_account()
    assert "not in the inventory" in report
    assert "ranks must be" in report
    assert "characters" in report


def test_validate_account_flags_leaked_sensitive_fields(workspace: Path, isolated_paths: Path) -> None:
    _materialized(workspace, isolated_paths)
    profile = json.loads((workspace / "account" / "profile.json").read_text())
    (workspace / "account" / "finance.json").write_text(
        json.dumps({"note": f"ssn {profile['ssn_last4']}"})
    )
    assert "sensitive profile value" in domain.validate_account()
