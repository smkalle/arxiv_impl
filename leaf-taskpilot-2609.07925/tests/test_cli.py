from __future__ import annotations

import json

import pytest

from leafcx import cli
from leafcx.scenarios import FAMILIES


def test_list_shows_every_family(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["list"]) == 0
    out = capsys.readouterr().out
    for family in FAMILIES:
        assert family in out


def test_show_prints_the_brief(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "shortlist_build", "--seed", "3"]) == 0
    out = capsys.readouterr().out
    assert "## What the customer said" in out
    assert "How you are graded" in out


def test_show_json_is_machine_readable(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["show", "trade_in", "--seed", "3", "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["family"] == "trade_in"
    assert payload["params"]["new_budget"] > payload["params"]["cash_budget"]


def test_materialize_then_gold_grades_clean(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["materialize", "consent_prefs", "--seed", "2", "--gold"]) == 0
    assert "reward=1" in capsys.readouterr().out


def test_run_with_the_gold_backend_exits_zero(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "test_drive", "--seed", "2", "--backend", "gold", "--quiet"]) == 0
    assert "reward=1" in capsys.readouterr().out


def test_run_with_the_noop_backend_exits_nonzero(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["run", "test_drive", "--seed", "2", "--backend", "noop", "--quiet"]) == 1


def test_eval_reports_a_solve_rate(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(
        ["eval", "--backend", "gold", "--families", "consent_prefs,trade_in", "--seeds", "1-2",
         "--no-transcript"]
    )
    assert code == 0
    assert "solved 4/4 = 100.0%" in capsys.readouterr().out


def test_validate_checks_task_wellposedness(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["validate", "--families", "finance_prequal", "--seeds", "1-2"]) == 0
    assert "2/2 tasks well-posed" in capsys.readouterr().out


def test_doctor_reports_offline_backends(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["doctor", "--backend", "gold"]) == 0
    out = capsys.readouterr().out
    assert "offline backend" in out
    assert "pytest:" in out


def test_seed_ranges_and_lists_parse() -> None:
    assert cli._parse_seeds("1-3") == [1, 2, 3]
    assert cli._parse_seeds("1,4,7") == [1, 4, 7]
    assert cli._parse_seeds("1-2,9") == [1, 2, 9]


def test_unknown_family_is_rejected() -> None:
    with pytest.raises(SystemExit):
        cli._families("not_a_family")
