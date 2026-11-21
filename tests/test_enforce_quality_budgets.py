"""``enforce_quality_budgets``: a budget gate that a selection cannot drop (issue #213).

Decision 2 of issue #153 keeps ``TOOL002`` as the only sign that ``--profile``, ``--select``, ``--ignore`` or
``ignored_rules`` dropped METRIC014, so a CI job could lose its gate unseen.  A policy that sets
``"enforce_quality_budgets": true`` makes the budgets mandatory: a run that does not select METRIC014 is a configuration
failure, ``TOOL001: configuration failed: BudgetGateDropped``, exit 2, before any input is read.  The default is false,
and a policy without the key behaves as before.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from ontolint import main
from ontolint.policy import Policy, PolicyBudgetError

KITCHEN = str(Path(__file__).parent / "fixtures" / "kitchen_sink.ttl")
BUDGET = {"class_definition_coverage": {"minimum": 0.99}}
FAILURE = 2


def _policy(tmp_path: Path, **extra: Any) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"quality_budgets": BUDGET, "enforce_quality_budgets": True, **extra}), encoding="utf-8")
    return path


def _run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    capsys.readouterr()
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


# --- the policy key ---------------------------------------------------------------------------------------------


def test_the_key_is_off_by_default_and_is_not_an_unknown_key() -> None:
    assert Policy().enforce_quality_budgets is False
    policy = Policy.from_mapping({"quality_budgets": BUDGET, "enforce_quality_budgets": True})
    assert policy.enforce_quality_budgets is True and policy.unknown_keys == ()
    assert Policy.from_mapping({"quality_budgets": BUDGET}).enforce_quality_budgets is False


@pytest.mark.parametrize(
    ("data", "message"),
    [
        ({"quality_budgets": BUDGET, "enforce_quality_budgets": "yes"}, "must be true or false"),
        ({"quality_budgets": BUDGET, "enforce_quality_budgets": 1}, "must be true or false"),
        ({"enforce_quality_budgets": True}, "sets no budget to enforce"),
        ({"quality_budgets": {}, "enforce_quality_budgets": True}, "sets no budget to enforce"),
        (
            {"quality_budgets": BUDGET, "enforce_quality_budgets": True, "ignored_rules": ["METRIC014"]},
            "ignores METRIC014",
        ),
    ],
)
def test_a_contradictory_or_malformed_key_is_a_policy_error(data: dict[str, Any], message: str) -> None:
    with pytest.raises(PolicyBudgetError, match=message):
        Policy.from_mapping(data)


def test_false_with_no_budget_is_fine() -> None:
    assert Policy.from_mapping({"enforce_quality_budgets": False}).enforce_quality_budgets is False


# --- the run ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "argv",
    [("--profile", "minimal"), ("--ignore", "METRIC014"), ("--select", "LEX"), ("--ignore", "METRIC")],
    ids=" ".join,
)
def test_a_selection_that_drops_metric014_fails_the_run_instead_of_warning(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    code, out, err = _run(capsys, "--config", str(_policy(tmp_path)), *argv, KITCHEN)
    assert (code, out) == (FAILURE, "")
    assert err.startswith("TOOL001: configuration failed: BudgetGateDropped: the policy sets enforce_quality_budgets")
    assert "TOOL002" not in err and "Traceback" not in err


def test_the_failure_comes_before_any_input_is_read(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = _run(capsys, "--config", str(_policy(tmp_path)), "--select", "LEX", str(tmp_path / "gone.ttl"))
    assert code == FAILURE and "BudgetGateDropped" in err and "INPUT001" not in err


def test_the_default_selection_runs_the_budgets_and_gates(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(capsys, "--config", str(_policy(tmp_path)), "--format", "json", KITCHEN)
    assert code == 1 and err == ""
    assert any(f["rule"] == "METRIC014" for f in json.loads(out)["findings"])


@pytest.mark.parametrize("argv", [("--select", "METRIC014"), ("--select", "METRIC"), ("--profile", "strict")])
def test_a_selection_that_keeps_metric014_is_accepted(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], argv: tuple[str, ...]
) -> None:
    code, _, err = _run(capsys, "--config", str(_policy(tmp_path)), *argv, KITCHEN)
    assert code == 1 and "BudgetGateDropped" not in err


def test_without_the_key_a_dropped_gate_is_still_only_a_notice(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"quality_budgets": BUDGET}), encoding="utf-8")
    code, _, err = _run(capsys, "--config", str(path), "--select", "METRIC001", KITCHEN)
    assert code == 0 and "TOOL002: warning" in err and "BudgetGateDropped" not in err


def test_a_policy_enforcing_budgets_that_does_not_exist_for_this_run_is_unaffected_without_budgets(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"enforce_quality_budgets": False}), encoding="utf-8")
    code, _, err = _run(capsys, "--config", str(path), "--select", "LEX", KITCHEN)
    assert "BudgetGateDropped" not in err and code in (0, 1)
