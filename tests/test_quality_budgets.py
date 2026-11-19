"""``quality_budgets``: explicit thresholds over measurements, and the one finding of their breach (METRIC014).

A budget bounds the value of a named measurement (``docs/quality-budgets.md``).  Absolute bounds are checked
here from the policy file to the report; the METRIC001-METRIC013 keys are the built-in budgets, whose table
:data:`ontolint.rules.bounds.BUILT_IN` is pinned against the rules, the policy and the measurement catalogue.
"""

# ruff: noqa: PLR2004

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ontolint import main
from ontolint.policy import METRIC_FIELDS, Budget, Policy, PolicyBudgetError
from ontolint.rules import measurements, metrics
from ontolint.rules.bounds import BUILT_IN, MAXIMUM, MINIMUM, breached

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
KITCHEN = str(FIXTURES / "kitchen_sink.ttl")
SHAPES = str(FIXTURES / "kitchen_shapes.ttl")


def _run(
    tmp_path: Path, budgets: Any, *argv: str, policy: dict[str, Any] | None = None, capsys: pytest.CaptureFixture[str]
) -> tuple[int, str, str]:
    config = tmp_path / "policy.json"
    config.write_text(json.dumps({**(policy or {}), "quality_budgets": budgets}), encoding="utf-8")
    capsys.readouterr()
    code = main(["--config", str(config), "--select", "METRIC", *argv, KITCHEN])  # the file has errors of its own
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _findings(out: str, rule: str = "METRIC014") -> list[dict[str, Any]]:
    return [f for f in json.loads(out)["findings"] if f["rule"] == rule]


# --- the policy key -------------------------------------------------------------------------------------------


def test_no_budget_is_the_default() -> None:
    assert Policy().quality_budgets == ()
    assert Policy.from_mapping({}).quality_budgets == ()
    assert Policy.from_mapping({"quality_budgets": {}}).quality_budgets == ()


def test_budgets_are_validated_and_sorted_by_measurement() -> None:
    policy = Policy.from_mapping(
        {"quality_budgets": {"unresolved_imports": {"maximum": 0}, "class_label_coverage": {"minimum": 0.95}}}
    )
    assert policy.quality_budgets == (
        Budget("class_label_coverage", minimum=0.95),
        Budget("unresolved_imports", maximum=0),
    )


@pytest.mark.parametrize(
    ("budgets", "message"),
    [
        ([], "quality_budgets must map"),
        ({"x": []}, "quality_budgets.x must be an object"),
        ({"x": {}}, "quality_budgets.x needs a minimum or a maximum"),
        ({"x": {"minimun": 1}}, "quality_budgets.x has no key 'minimun'"),
        ({"x": {"delta": {"regressed": {"maximum": 0}}}}, "quality_budgets.x has no key 'delta'"),
        ({"x": {"minimum": -0.1}}, "quality_budgets.x.minimum must be at least 0"),
        ({"x": {"maximum": math.inf}}, "quality_budgets.x.maximum must be a finite number"),
        ({"x": {"maximum": math.nan}}, "quality_budgets.x.maximum must be a finite number"),
        ({"x": {"maximum": True}}, "quality_budgets.x.maximum must be a finite number"),
        ({"x": {"minimum": "0.5"}}, "quality_budgets.x.minimum must be a finite number"),
        ({"x": {"minimum": None}}, "quality_budgets.x.minimum must be a finite number"),
        ({"x": {"minimum": 0.9, "maximum": 0.5}}, "quality_budgets.x: minimum 0.9 exceeds maximum 0.5"),
    ],
)
def test_malformed_budgets_are_refused(budgets: Any, message: str) -> None:
    with pytest.raises(PolicyBudgetError, match=message):
        Policy.from_mapping({"quality_budgets": budgets})


def test_an_equal_minimum_and_maximum_pin_a_value() -> None:
    assert Policy.from_mapping({"quality_budgets": {"x": {"minimum": 2, "maximum": 2}}}).quality_budgets[0].maximum == 2


@pytest.mark.parametrize(
    ("budgets", "message"),
    [
        ({"nonsense": {"maximum": 0}}, "unknown measurement 'nonsense'"),
        ({"class_depth": {"maximum": 3}}, "class_depth is a histogram"),
        ({"unresolved_imports": {"maximum": 0.5}}, "unresolved_imports counts: its bounds are integers"),
        ({"class_label_coverage": {"minimum": 95}}, "class_label_coverage is a share: its bounds are at most 1"),
    ],
)
def test_a_budget_that_cannot_apply_is_a_gov020_configuration_error(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], budgets: Any, message: str
) -> None:
    code, out, err = _run(tmp_path, budgets, "--format", "json", capsys=capsys)
    assert (code, out) == (2, "")
    assert err.startswith("GOV020: policy file rejected: quality_budgets")
    assert message in err


def test_a_malformed_budget_is_a_gov020_error_too(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(tmp_path, {"unresolved_imports": {"maximum": -1}}, capsys=capsys)
    assert (code, out) == (2, "")
    assert err.startswith("GOV020: policy file rejected: quality_budgets.unresolved_imports.maximum must be at least 0")


def test_the_key_is_not_an_unknown_key() -> None:
    assert Policy.from_mapping({"quality_budgets": {"unresolved_imports": {"maximum": 0}}}).unknown_keys == ()


# --- the comparison -----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("value", "side", "limit", "expected"),
    [
        (0.95, MINIMUM, 0.95, False),
        (0.9499, MINIMUM, 0.95, True),
        (0.9501, MINIMUM, 0.95, False),
        (3, MAXIMUM, 3, False),
        (4, MAXIMUM, 3, True),
        (2, MAXIMUM, 3, False),
        (0.0, MAXIMUM, 0, False),
    ],
)
def test_bounds_are_inclusive(value: float, side: str, limit: float, expected: bool) -> None:
    assert breached(value, side, limit) is expected


@given(st.floats(min_value=0, max_value=1e9, allow_nan=False), st.floats(min_value=0, max_value=1e9, allow_nan=False))
def test_the_two_bounds_are_complements_of_the_limit(value: float, limit: float) -> None:
    assert breached(value, MAXIMUM, limit) == (value > limit)
    assert breached(value, MINIMUM, limit) == (value < limit)
    assert not breached(limit, MAXIMUM, limit)  # a value at its limit is within the budget
    assert not breached(limit, MINIMUM, limit)
    # Within a minimum and a maximum that differ, a value is in the budget exactly when neither is breached.
    assert not (breached(value, MINIMUM, limit) and breached(value, MAXIMUM, limit))


# --- absolute bounds, from the policy file to the report -----------------------------------------------------


def test_a_maximum_breach_is_one_baselinable_finding(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(tmp_path, {"unresolved_imports": {"maximum": 0}}, "--format", "json", capsys=capsys)
    (finding,) = _findings(out)
    assert code == 1  # an error, so it gates
    assert finding["message"] == "unresolved_imports is 1, above the maximum 0."
    assert (finding["severity"], finding["confidence"]) == ("error", "certain")
    assert finding["focus"] == "https://example.test/onto.owl"  # the ontology, as every METRIC finding


def test_a_value_at_its_maximum_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(tmp_path, {"unresolved_imports": {"maximum": 1}}, "--format", "json", capsys=capsys)
    assert _findings(out) == []
    assert code == 0


def test_a_minimum_breach_names_the_counts(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(tmp_path, {"class_definition_coverage": {"minimum": 0.95}}, "--format", "json", capsys=capsys)
    (finding,) = _findings(out)
    assert code == 1
    assert finding["message"] == "class_definition_coverage is 0.18 (6 of 33), below the minimum 0.95."


def test_a_value_at_its_minimum_passes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    for minimum, breaches in ((1, False), (2, True)):
        _, out, _ = _run(tmp_path, {"unresolved_imports": {"minimum": minimum}}, "--format", "json", capsys=capsys)
        assert bool(_findings(out)) is breaches


def test_only_the_bound_a_value_breaches_is_reported(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    budgets = {"class_label_coverage": {"minimum": 0.1, "maximum": 0.5}}
    _, out, _ = _run(tmp_path, budgets, "--format", "json", capsys=capsys)
    assert [f["message"] for f in _findings(out)] == [
        "class_label_coverage is 0.97 (32 of 33), above the maximum 0.50.",
    ]


def test_an_empty_population_breaches_nothing(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # foreign_references is 0 of 36 here; on a graph without classes a ratio is over nothing, so it is not measured.
    empty = tmp_path / "empty.ttl"
    empty.write_text("<https://e.test/o> a <http://www.w3.org/2002/07/owl#Ontology> .\n", encoding="utf-8")
    config = tmp_path / "p.json"
    config.write_text(json.dumps({"quality_budgets": {"class_label_coverage": {"minimum": 1}}}), encoding="utf-8")
    code = main(["--config", str(config), "--format", "json", str(empty)])
    assert (code, _findings(capsys.readouterr().out)) == (0, [])


def test_a_budget_is_not_gated_by_the_metric_sample_size(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # 6 classes are defined: below metric_min_sample (10), which silences METRIC012, not an explicit budget.
    _, out, _ = _run(tmp_path, {"definition_length": {"minimum": 100}}, "--format", "json", capsys=capsys)
    assert len(_findings(out)) == 1
    assert _findings(out, "METRIC012") == []


def test_budgets_are_evaluated_without_the_measurements_flag(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _, out, _ = _run(tmp_path, {"unresolved_imports": {"maximum": 0}}, "--format", "json", capsys=capsys)
    assert "measurements" not in json.loads(out)["files"][0]


def test_the_severity_can_be_lowered(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = _run(
        tmp_path,
        {"unresolved_imports": {"maximum": 0}},
        "--format",
        "json",
        policy={"severity_overrides": {"METRIC014": "info"}},
        capsys=capsys,
    )
    assert [f["severity"] for f in _findings(out)] == ["info"]
    assert code == 0


# --- renderings --------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", ["text", "sarif", "markdown"])
def test_a_breach_renders_in_every_format(tmp_path: Path, capsys: pytest.CaptureFixture[str], fmt: str) -> None:
    code, out, _ = _run(tmp_path, {"unresolved_imports": {"maximum": 0}}, "--format", fmt, capsys=capsys)
    assert code == 1
    assert "METRIC014" in out
    assert "unresolved_imports is 1, above the maximum 0." in out


def test_the_sarif_result_names_the_rule(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _, out, _ = _run(tmp_path, {"unresolved_imports": {"maximum": 0}}, "--format", "sarif", capsys=capsys)
    results = [r for r in json.loads(out)["runs"][0]["results"] if r["ruleId"] == "METRIC014"]
    assert [r["level"] for r in results] == ["error"]


# --- the baseline ---------------------------------------------------------------------------------------------------


def test_a_breach_is_suppressed_by_its_baseline_and_a_new_one_is_not(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    baseline = tmp_path / "baseline.json"
    config = tmp_path / "policy.json"

    def budgets(**named: dict[str, float]) -> None:
        config.write_text(json.dumps({"quality_budgets": named}), encoding="utf-8")

    budgets(class_definition_coverage={"minimum": 0.95})
    assert main(["--config", str(config), "--write-baseline", str(baseline), "--select", "METRIC014", KITCHEN]) == 1
    capsys.readouterr()
    args = ["--config", str(config), "--baseline", str(baseline), "--select", "METRIC014", KITCHEN]
    assert main(args) == 0  # accepted
    # The value and the limit are not in the identity: a looser bound that is still breached stays accepted.
    budgets(class_definition_coverage={"minimum": 0.5})
    assert main(args) == 0
    # Another bound of the same measurement is another finding, and so is another measurement.
    budgets(class_definition_coverage={"maximum": 0.1})
    assert main(args) == 1
    budgets(class_definition_coverage={"minimum": 0.95}, class_label_coverage={"maximum": 0.5})
    assert main(args) == 1


# --- an untaken measurement ----------------------------------------------------------------------------------------


def test_a_budget_on_an_untaken_measurement_exits_2_with_the_report_written(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, err = _run(
        tmp_path,
        {"shacl_class_target_coverage": {"minimum": 0}},  # a minimum of 0 can never be breached
        "--format",
        "json",
        capsys=capsys,
    )
    assert code == 2
    assert "TOOL001: rule METRIC014 failed" in err
    assert "shacl_class_target_coverage: no SHACL shapes graph was supplied" in err
    assert json.loads(out)["findings"]  # the report is still written


def test_an_untaken_budget_never_passes_on_a_value_it_could_not_read(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(
        tmp_path,
        {"shacl_class_target_coverage": {"minimum": 0}, "unresolved_imports": {"maximum": 0}},
        "--format",
        "json",
        "--fail-on",
        "never",
        capsys=capsys,
    )
    assert code == 2  # even with --fail-on never
    assert _findings(out) == []  # no verdict from the rule, not a partial one


def test_the_other_metric_rules_keep_their_findings_when_a_budget_is_untaken(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out, _ = _run(
        tmp_path,
        {"shacl_class_target_coverage": {"minimum": 0}},
        "--format",
        "json",
        policy={"metric_max_orphan_ratio": 0.1},
        capsys=capsys,
    )
    assert code == 2
    assert _findings(out, "METRIC005")


def test_a_budget_on_a_measurement_with_shapes_is_taken(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = _run(
        tmp_path, {"shacl_class_target_coverage": {"minimum": 0}}, "--shapes", SHAPES, "--format", "json", capsys=capsys
    )
    assert (code, err) == (0, "")
    assert _findings(out) == []


# --- the built-in budgets -------------------------------------------------------------------------------------------


def test_every_metric_key_is_one_built_in_budget() -> None:
    keys = [b.key for b in BUILT_IN]
    assert sorted(keys) == sorted(set(METRIC_FIELDS) - {"metric_min_sample"})
    assert [b.rule for b in BUILT_IN] == [spec.rule_id for spec in metrics.SPECS]
    for built_in in BUILT_IN:
        assert built_in.side in (MINIMUM, MAXIMUM)
        assert built_in.key.startswith(f"metric_{built_in.side[:3]}_")  # metric_max_..., metric_min_...
        assert built_in.rule in measurements.spec_of(built_in.measurement).rules


#: ``(policy key, measurement, limits)`` for the built-in budgets whose measurement is a share (or a count) of
#: the kitchen sink, so that a METRIC rule and the budget over the same value can be compared on one file.
EQUIVALENT = [
    ("metric_max_orphan_ratio", "orphan_classes", (0.0, 0.1, 6 / 33, 0.3)),
    ("metric_max_unsigned_property_ratio", "unsigned_properties", (0.0, 0.2, 3 / 14, 0.5)),
    ("metric_min_language_coverage", "label_language_coverage", (0.0, 0.04, 2 / 46, 0.5)),
    ("metric_max_blank_node_ratio", "blank_subjects", (0.0, 0.5)),
    ("metric_max_imports", "unresolved_imports", (0, 1, 2)),
    ("metric_max_mean_fanout", "class_fanout", (0.5, 15 / 14, 2.0)),
    ("metric_max_property_class_ratio", "relation_properties_per_class", (0.1, 14 / 33, 1.0)),
    ("metric_min_property_class_ratio", "relation_properties_per_class", (0.1, 14 / 33, 1.0)),
    ("metric_min_definition_words", "definition_length", (1.0, 7 / 6, 2.0)),
]


@pytest.mark.parametrize(("key", "measurement", "limits"), EQUIVALENT)
def test_a_budget_over_the_value_a_metric_key_limits_breaches_exactly_when_the_rule_fires(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], key: str, measurement: str, limits: tuple[float, ...]
) -> None:
    (built_in,) = (b for b in BUILT_IN if b.key == key)
    for limit in limits:
        config = {key: limit, "metric_min_sample": 1}
        _, out, _ = _run(
            tmp_path, {measurement: {built_in.side: limit}}, "--format", "json", policy=config, capsys=capsys
        )
        assert bool(_findings(out)) == bool(_findings(out, built_in.rule)), (key, limit)


def test_the_metric_findings_of_the_default_policy_are_those_of_a_policy_with_no_budget(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["--select", "METRIC", "--format", "json", KITCHEN]) == 0
    plain = json.loads(capsys.readouterr().out)["findings"]
    _, out, _ = _run(tmp_path, {}, "--format", "json", capsys=capsys)
    assert json.loads(out)["findings"] == plain
    assert not any(f["rule"] == "METRIC014" for f in plain)
