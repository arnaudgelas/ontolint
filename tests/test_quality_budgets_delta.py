"""Delta budgets: bounds over the classified change against a quality baseline (issues #148 and #98).

``quality_budgets.<measurement>.delta`` bounds the terms that ``regressed``, were ``diluted`` or ``removed`` (maximum
counts) and the share of the new terms that are fine, ``new_terms`` (minimum).  A breach is a finding of METRIC014, so
severity, ``--baseline`` and ``--fail-on`` act on it; a run it cannot judge is exit 2, never a pass.  The fixtures
are those of ``tests/test_quality_cli.py``: ``after.ttl`` against ``before.ttl`` regressed 1, diluted 3 and removed 2
of ``class_definition_coverage``; ``grown.ttl`` added one fine term and one that is not.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from rdflib import Graph

from ontolint import Linter, main
from ontolint.models import ExecutionStatus
from ontolint.policy import DeltaBudget, Policy, PolicyBudgetError

FIXTURES = Path(__file__).parent / "fixtures" / "quality"
BEFORE, AFTER, GROWN = (str(FIXTURES / f"{name}.ttl") for name in ("before", "after", "grown"))
COVERAGE = "class_definition_coverage"
RULE = "METRIC014"
FAILURE = 2  # a tool failure, a policy error and a usage error all exit 2


@pytest.fixture
def baseline(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> Path:
    """The quality snapshot of ``before.ttl``, the accepted values."""
    path = tmp_path / "quality.json"
    assert main([BEFORE, "--select", RULE, "--write-quality-snapshot", str(path)]) == 0
    capsys.readouterr()
    return path


def _policy(tmp_path: Path, delta: dict[str, Any], **budget: Any) -> Path:
    path = tmp_path / "policy.json"
    path.write_text(json.dumps({"quality_budgets": {COVERAGE: {**budget, "delta": delta}}}), encoding="utf-8")
    return path


def _run(
    capsys: pytest.CaptureFixture[str], policy: Path, base: Path | None, source: str = AFTER, *extra: str
) -> tuple[int, str, str]:
    args = [source, "--config", str(policy), "--select", RULE, *(["--quality-baseline", str(base)] if base else [])]
    capsys.readouterr()
    code = main([*args, *extra])
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _findings(out: str) -> list[dict[str, Any]]:
    return [f for f in json.loads(out)["findings"] if f["rule"] == RULE]


# --- the policy key ---------------------------------------------------------------------------------------------


def test_a_delta_is_parsed_with_its_four_bounds() -> None:
    delta = {
        "regressed": {"maximum": 0},
        "diluted": {"maximum": 2},
        "removed": {"maximum": 5},
        "new_terms": {"minimum": 0.8},
    }
    budget = Policy.from_mapping({"quality_budgets": {COVERAGE: {"delta": delta}}}).quality_budgets[0]
    assert budget.delta == DeltaBudget(regressed=0, diluted=2, removed=5, new_terms=0.8)
    assert (budget.minimum, budget.maximum) == (None, None)  # a budget with a delta alone is a budget


def test_a_delta_beside_absolute_bounds_is_one_budget() -> None:
    budget = Policy.from_mapping(
        {"quality_budgets": {COVERAGE: {"minimum": 0.9, "delta": {"regressed": {"maximum": 0}}}}}
    ).quality_budgets[0]
    assert (budget.minimum, budget.delta) == (0.9, DeltaBudget(regressed=0))


def test_a_policy_names_its_delta_budgets() -> None:
    policy = Policy.from_mapping(
        {"quality_budgets": {COVERAGE: {"delta": {"removed": {"maximum": 1}}}, "unresolved_imports": {"maximum": 0}}}
    )
    assert [b.measurement for b in policy.delta_budgets] == [COVERAGE]
    assert Policy().delta_budgets == ()


@pytest.mark.parametrize(
    ("delta", "message"),
    [
        ([], "quality_budgets.x.delta must be an object with at least one of regressed, diluted, removed, new_terms"),
        ({}, "quality_budgets.x.delta must be an object with at least one of"),
        ({"lost": {"maximum": 0}}, "quality_budgets.x.delta has no key 'lost'; its keys are regressed, diluted"),
        ({"regressed": 0}, "quality_budgets.x.delta.regressed must be an object with a maximum only"),
        ({"regressed": {"minimum": 0}}, "quality_budgets.x.delta.regressed must be an object with a maximum only"),
        ({"regressed": {"maximum": 0, "minimum": 0}}, "regressed must be an object with a maximum only"),
        (
            {"regressed": {"maximum": -1}},
            "quality_budgets.x.delta.regressed.maximum must be a whole number of at least 0",
        ),
        ({"diluted": {"maximum": 1.5}}, "quality_budgets.x.delta.diluted.maximum must be a whole number of at least 0"),
        (
            {"removed": {"maximum": True}},
            "quality_budgets.x.delta.removed.maximum must be a whole number of at least 0",
        ),
        ({"new_terms": {"maximum": 0.5}}, "quality_budgets.x.delta.new_terms must be an object with a minimum only"),
        ({"new_terms": {"minimum": 80}}, "quality_budgets.x.delta.new_terms.minimum must be a share between 0 and 1"),
        ({"new_terms": {"minimum": -0.1}}, "new_terms.minimum must be a share between 0 and 1"),
        ({"new_terms": {"minimum": "0.8"}}, "quality_budgets.x.delta.new_terms.minimum must be a finite number"),
        ({"new_terms": {"minimum": True}}, "quality_budgets.x.delta.new_terms.minimum must be a finite number"),
        ({"new_terms": {"minimum": float("nan")}}, "new_terms.minimum must be a finite number"),
    ],
)
def test_a_malformed_delta_is_refused(delta: Any, message: str) -> None:
    with pytest.raises(PolicyBudgetError, match=message):
        Policy.from_mapping({"quality_budgets": {"x": {"delta": delta}}})


@pytest.mark.parametrize(
    ("measurement", "message"),
    [
        ("unresolved_imports", "unresolved_imports has no terms; a delta bounds a coverage measure"),
        ("class_fanout", "class_fanout has no terms; a delta bounds a coverage measure"),
        ("class_depth", "class_depth is a histogram"),
    ],
)
def test_a_delta_needs_a_coverage_measure(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], measurement: str, message: str
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"quality_budgets": {measurement: {"delta": {"regressed": {"maximum": 0}}}}}), encoding="utf-8"
    )
    code, out, err = _run(capsys, policy, None)
    assert (code, out) == (FAILURE, "")
    assert err.startswith("GOV020: policy file rejected: quality_budgets.") and message in err


# --- each delta key, passing and failing ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("bound", "breached"),
    [
        (("regressed", 0), True),
        (("regressed", 1), False),  # inclusive: a count equal to its maximum passes
        (("diluted", 2), True),
        (("diluted", 3), False),
        (("removed", 1), True),
        (("removed", 2), False),
    ],
)
def test_a_count_over_its_maximum_is_a_finding(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path, bound: tuple[str, int], breached: bool
) -> None:
    key, limit = bound
    code, out, err = _run(capsys, _policy(tmp_path, {key: {"maximum": limit}}), baseline, AFTER, "--format", "json")
    assert (code, len(_findings(out))) == ((1, 1) if breached else (0, 0))
    assert err == ""


def test_the_message_names_the_count_the_baseline_and_the_limit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    policy = _policy(tmp_path, {"regressed": {"maximum": 0}, "diluted": {"maximum": 0}, "removed": {"maximum": 0}})
    _, out, _ = _run(capsys, policy, baseline, AFTER, "--format", "json")
    messages = sorted(f["message"] for f in _findings(out))
    assert messages == [
        f"{COVERAGE}: 1 term got worse since the quality baseline, above the maximum 0.",
        f"{COVERAGE}: 2 terms were removed since the quality baseline, above the maximum 0.",
        f"{COVERAGE}: 3 new terms are not fine since the quality baseline, above the maximum 0.",
    ]
    assert {(f["severity"], f["confidence"]) for f in _findings(out)} == {("error", "certain")}


def test_a_single_dilution_reads_in_the_singular(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    _, out, _ = _run(capsys, _policy(tmp_path, {"diluted": {"maximum": 0}}), baseline, GROWN, "--format", "json")
    assert [f["message"] for f in _findings(out)] == [
        f"{COVERAGE}: 1 new term is not fine since the quality baseline, above the maximum 0."
    ]


@pytest.mark.parametrize(("limit", "breached"), [(0.5, False), (0.6, True), (0, False)])
def test_the_share_of_fine_new_terms_has_a_minimum(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path, limit: float, breached: bool
) -> None:
    code, out, _ = _run(
        capsys, _policy(tmp_path, {"new_terms": {"minimum": limit}}), baseline, GROWN, "--format", "json"
    )
    assert (code, len(_findings(out))) == ((1, 1) if breached else (0, 0))
    if breached:
        assert _findings(out)[0]["message"] == (
            f"{COVERAGE}: the share of new terms that are fine is 0.50 (1 of 2) since the quality baseline, "
            "below the minimum 0.60."
        )


def test_no_new_terms_is_no_share_and_breaches_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    code, out, _ = _run(capsys, _policy(tmp_path, {"new_terms": {"minimum": 1}}), baseline, BEFORE, "--format", "json")
    assert (code, _findings(out)) == (0, [])


def test_only_dilution_counts_against_the_share(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    """after.ttl adds three terms that are not fine and none that is: the share is 0 of 3."""
    code, out, _ = _run(capsys, _policy(tmp_path, {"new_terms": {"minimum": 0.1}}), baseline, AFTER, "--format", "json")
    assert code == 1
    assert "is 0.00 (0 of 3)" in _findings(out)[0]["message"]


def test_a_budget_not_breached_by_a_change_reports_nothing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    delta = {
        "regressed": {"maximum": 1},
        "diluted": {"maximum": 3},
        "removed": {"maximum": 2},
        "new_terms": {"minimum": 0},
    }
    code, out, err = _run(capsys, _policy(tmp_path, delta), baseline, AFTER, "--format", "json")
    assert (code, _findings(out), err) == (0, [], "")


def test_delta_and_absolute_bounds_are_both_judged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    policy = _policy(tmp_path, {"regressed": {"maximum": 0}}, minimum=0.95)
    _, out, _ = _run(capsys, policy, baseline, AFTER, "--format", "json")
    assert sorted(f["message"] for f in _findings(out)) == [
        f"{COVERAGE} is 0.33 (2 of 6), below the minimum 0.95.",
        f"{COVERAGE}: 1 term got worse since the quality baseline, above the maximum 0.",
    ]


# --- a change that cannot be judged is exit 2 -----------------------------------------------------------------------


def test_a_delta_budget_without_a_quality_baseline_is_a_policy_error_before_any_input_is_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(capsys, _policy(tmp_path, {"regressed": {"maximum": 0}}), None, str(tmp_path / "gone.ttl"))
    assert (code, out) == (FAILURE, "")
    assert err == f"GOV020: policy file rejected: quality_budgets.{COVERAGE}.delta needs --quality-baseline FILE\n"


def test_a_baseline_that_cannot_be_compared_is_exit_2_with_the_report_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    other = json.loads(baseline.read_text(encoding="utf-8"))
    other["policy"]["base"] = "https://elsewhere.example/"  # another owned population
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(other), encoding="utf-8")
    code, out, err = _run(capsys, _policy(tmp_path, {"regressed": {"maximum": 9}}), changed, AFTER, "--format", "json")
    assert (
        code == FAILURE and json.loads(out)["findings"] == []
    )  # a delta budget never passes on a change it could not read
    assert f"TOOL001: rule {RULE} failed" in err
    assert f"{COVERAGE}: cannot be compared with the quality baseline (policy differs: base)" in err
    assert "write a new one with --write-quality-snapshot" in err


def test_a_definition_version_change_is_not_comparable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    other = json.loads(baseline.read_text(encoding="utf-8"))
    entry = next(m for m in other["measurements"] if m["id"] == COVERAGE)
    entry["definition_version"] += 1
    changed = tmp_path / "changed.json"
    changed.write_text(json.dumps(other), encoding="utf-8")
    code, _, err = _run(capsys, _policy(tmp_path, {"removed": {"maximum": 99}}), changed, AFTER, "--format", "json")
    assert code == FAILURE and "definition version" in err


def test_a_measurement_that_was_not_taken_is_not_comparable(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    """The SHACL coverage needs a shapes graph: neither the baseline run nor this one has it, so it has no change."""
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps({"quality_budgets": {"shacl_class_target_coverage": {"delta": {"regressed": {"maximum": 0}}}}}),
        encoding="utf-8",
    )
    snapshot = tmp_path / "quality.json"
    assert main([BEFORE, "--write-quality-snapshot", str(snapshot), "--select", RULE]) == 0
    capsys.readouterr()
    code, _, err = _run(capsys, policy, snapshot, AFTER, "--format", "json")
    assert code == FAILURE
    assert (
        "shacl_class_target_coverage: cannot be compared with the quality baseline (not taken in the old snapshot"
        in err
    )


def test_a_change_on_one_measurement_is_not_judged_by_a_neighbour_that_cannot_be_compared(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    """Every delta budget is read before any is compared: one that cannot be read fails the run, none reports partly."""
    policy = tmp_path / "policy.json"
    budgets = {
        COVERAGE: {"delta": {"regressed": {"maximum": 0}}},
        "shacl_class_target_coverage": {"delta": {"regressed": {"maximum": 0}}},
    }
    policy.write_text(json.dumps({"quality_budgets": budgets}), encoding="utf-8")
    code, out, _ = _run(capsys, policy, baseline, AFTER, "--format", "json")
    assert code == FAILURE and _findings(out) == []


def test_the_python_api_without_a_comparison_fails_the_rule() -> None:
    """``RuleContext.quality_comparison`` is set by the command line; a caller that has none gets a failed rule."""
    policy = Policy.from_mapping({"quality_budgets": {COVERAGE: {"delta": {"regressed": {"maximum": 0}}}}})
    result = Linter(Graph(), policy=policy).execute([RULE])
    assert [(e.rule_id, e.status) for e in result.executions] == [(RULE, ExecutionStatus.FAILED)]
    assert "a delta budget needs a quality baseline" in result.executions[0].detail


# --- the finding is an ordinary one ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["text", "json", "sarif", "markdown"])
def test_a_breach_renders_in_every_format(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path, fmt: str
) -> None:
    """A baseline that gates needs no format that shows the comparison: text and SARIF accept it too."""
    code, out, err = _run(capsys, _policy(tmp_path, {"regressed": {"maximum": 0}}), baseline, AFTER, "--format", fmt)
    assert (code, err) == (1, "")
    assert "1 term got worse since the quality baseline" in out
    if fmt == "sarif":
        assert json.loads(out)["runs"][0]["results"][0]["ruleId"] == RULE


def test_the_comparison_still_shows_in_json_and_markdown(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    policy = _policy(tmp_path, {"regressed": {"maximum": 0}})
    assert "quality_comparison" in json.loads(_run(capsys, policy, baseline, AFTER, "--format", "json")[1])
    assert "### Quality against the baseline" in _run(capsys, policy, baseline, AFTER, "--format", "markdown")[1]


def test_a_breach_is_suppressed_by_a_baseline_and_a_new_one_is_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    policy = _policy(tmp_path, {"regressed": {"maximum": 0}})
    accepted = tmp_path / "findings.json"
    assert _run(capsys, policy, baseline, AFTER, "--write-baseline", str(accepted))[0] == 1
    assert _run(capsys, policy, baseline, AFTER, "--baseline", str(accepted))[0] == 0
    # The counts are not in the identity, so a worse change under the same budget stays accepted ...
    assert (
        _run(capsys, _policy(tmp_path, {"regressed": {"maximum": 0}}), baseline, AFTER, "--baseline", str(accepted))[0]
        == 0
    )
    # ... and another delta key of the same measurement is a new finding.
    other = _policy(tmp_path, {"regressed": {"maximum": 0}, "removed": {"maximum": 0}})
    assert _run(capsys, other, baseline, AFTER, "--baseline", str(accepted))[0] == 1


def test_the_severity_can_be_lowered(tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(
        json.dumps(
            {
                "quality_budgets": {COVERAGE: {"delta": {"regressed": {"maximum": 0}}}},
                "severity_overrides": {RULE: "info"},
            }
        ),
        encoding="utf-8",
    )
    code, out, _ = _run(capsys, policy, baseline, AFTER, "--format", "json")
    assert (code, [f["severity"] for f in _findings(out)]) == (0, ["info"])


def test_dropping_metric014_warns_and_checks_no_delta_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    policy = _policy(tmp_path, {"regressed": {"maximum": 0}})
    capsys.readouterr()
    assert main([AFTER, "--config", str(policy), "--quality-baseline", str(baseline), "--select", "METRIC001"]) == 0
    assert "METRIC014 is not selected" in capsys.readouterr().err


# --- the options ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["text", "sarif"])
def test_without_a_delta_budget_a_baseline_still_needs_a_format_that_shows_it(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path, fmt: str
) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"quality_budgets": {COVERAGE: {"minimum": 0.1}}}), encoding="utf-8")
    with pytest.raises(SystemExit) as exit_:
        _run(capsys, policy, baseline, AFTER, "--format", fmt)
    assert exit_.value.code == FAILURE
    assert "unless the policy has a delta budget" in capsys.readouterr().err


def test_a_run_without_delta_budgets_is_unchanged(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], baseline: Path
) -> None:
    """The comparison is not built for a run that does not gate on it, so nothing about the report moves."""
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"quality_budgets": {COVERAGE: {"minimum": 0.1}}}), encoding="utf-8")
    with_baseline = _run(capsys, policy, baseline, AFTER, "--format", "json")
    plain = _run(capsys, policy, None, AFTER, "--format", "json")
    assert json.loads(with_baseline[1]).pop("quality_comparison") and with_baseline[0] == plain[0]
