"""Distributions, readings and the limits the labels allow (scripts/metric_corpus.py, docs/metric-calibration.md).

The corpus itself is not fetched here: the recorded results and a tiny fixture stand in for it, so this runs offline.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from fractions import Fraction
from pathlib import Path
from typing import Any

import pytest

from ontolint.policy import Policy

ROOT = Path(__file__).parent.parent
spec = importlib.util.spec_from_file_location("metric_corpus", ROOT / "scripts" / "metric_corpus.py")
assert spec is not None
assert spec.loader is not None
metric_corpus = importlib.util.module_from_spec(spec)
sys.modules["metric_corpus"] = metric_corpus
spec.loader.exec_module(metric_corpus)

# Ten owned classes: four labelled, C1-C3 under C0, one object property with a domain and no documentation.
FIXTURE = """\
@prefix : <https://example.test/o#> .
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

<https://example.test/o> a owl:Ontology .
:C0 a owl:Class ; rdfs:label "zero"@en .
:C1 a owl:Class ; rdfs:subClassOf :C0 ; rdfs:label "one"@en .
:C2 a owl:Class ; rdfs:subClassOf :C0 ; rdfs:label "two" .
:C3 a owl:Class ; rdfs:subClassOf :C0 ; rdfs:label "three" .
:C4 a owl:Class . :C5 a owl:Class . :C6 a owl:Class . :C7 a owl:Class . :C8 a owl:Class . :C9 a owl:Class .
:p a owl:ObjectProperty ; rdfs:domain :C0 .
"""


def _results() -> dict[str, Any]:
    return json.loads(metric_corpus.RESULTS.read_text(encoding="utf-8"))


def _vector(**cells: tuple[int, int] | int) -> dict[str, dict[str, int]]:
    """A measurement vector for ``reading``: ``name=(numerator, denominator)`` or ``name=count``."""
    return {
        name: (
            {"definition_version": 1, "numerator": cell[0], "denominator": cell[1]}
            if isinstance(cell, tuple)
            else {"definition_version": 1, "value": cell}
        )
        for name, cell in cells.items()
    }


@pytest.mark.parametrize(
    ("rule", "vector", "expected"),
    [
        # Coverage measurements count what is present; the rule reads what is missing.
        ("METRIC001", _vector(class_label_coverage=(4, 10)), Fraction(6, 10)),
        ("METRIC001", _vector(class_label_coverage=(0, 0)), None),
        ("METRIC001", _vector(class_label_coverage=(3, 9)), None),  # below the sample gate of 10
        ("METRIC003", _vector(property_documentation_coverage=(0, 12)), Fraction(1)),
        ("METRIC004", _vector(class_fanout=(9, 3), orphan_classes=(0, 10)), Fraction(3)),
        ("METRIC004", _vector(class_fanout=(0, 0), orphan_classes=(0, 10)), None),  # no parent, no finding
        ("METRIC004", _vector(class_fanout=(9, 3), orphan_classes=(0, 9)), None),  # gated on the classes
        ("METRIC009", _vector(label_language_coverage=(2, 10)), Fraction(1, 5)),
        ("METRIC011", _vector(unresolved_imports=3), Fraction(3)),
        ("METRIC011", _vector(unresolved_imports=0), Fraction(0)),  # no sample gate
    ],
)
def test_a_reading_follows_the_rule_and_its_sample_gate(
    rule: str, vector: dict[str, dict[str, int]], expected: Fraction | None
) -> None:
    assert metric_corpus.reading(rule, vector, 10) == expected


def test_every_rule_reads_a_measurement_the_engine_publishes() -> None:
    assert set(metric_corpus.READINGS) == set(metric_corpus.RULES)
    lines = (ROOT / "docs" / "measurements.md").read_text(encoding="utf-8").splitlines()
    published = {line.split("`")[1] for line in lines if line.startswith("| `")}
    for read in metric_corpus.READINGS.values():
        assert read.measurement in published
        assert read.gate is None or read.gate in published


def test_the_limits_and_the_sample_gate_are_the_policy_defaults() -> None:
    policy = Policy()
    limits = metric_corpus.default_limits()
    assert set(limits) == set(metric_corpus.RULES)
    for rule, key in metric_corpus.LIMIT_KEYS.items():
        assert limits[rule] == Fraction(getattr(policy, key))
    assert metric_corpus.sample_gate() == policy.metric_min_sample


def test_the_distribution_of_a_few_values_is_exact_and_interpolated() -> None:
    values = [Fraction(n) for n in (1, 2, 3, 4, 10)]
    assert metric_corpus.describe(values) == {
        "n": 5,
        "min": Fraction(1),
        "q1": Fraction(2),
        "median": Fraction(3),
        "q3": Fraction(4),
        "max": Fraction(10),
    }
    assert metric_corpus.describe([Fraction(2), Fraction(1)])["q1"] == Fraction(5, 4)  # order does not matter
    single = metric_corpus.describe([Fraction(7)])
    assert single == {"n": 1, **dict.fromkeys(("min", "q1", "median", "q3", "max"), Fraction(7))}
    assert metric_corpus.describe([]) == {"n": 0}


def _labelled(spec: dict[str, tuple[str, Fraction]]) -> tuple[list[Any], dict[str, Fraction]]:
    entries = [
        metric_corpus.Entry(name, "", "", {"*": {"expect": expect, "basis": "checked", "why": "x"}})
        for name, (expect, _) in spec.items()
    ]
    return entries, {name: value for name, (_, value) in spec.items()}


@pytest.mark.parametrize(
    ("rule", "spec", "expected"),
    [
        # an upper limit fires above it: every silent value <= limit < every fire value
        ("METRIC002", {"a": ("silent", Fraction(3, 10)), "b": ("fire", Fraction(9, 10))}, "[0.3000, 0.9000)"),
        ("METRIC002", {"a": ("silent", Fraction(9, 10)), "b": ("fire", Fraction(3, 10))}, "none"),
        ("METRIC002", {"a": ("silent", Fraction(3, 10))}, "[0.3000, +inf)"),
        ("METRIC002", {"b": ("fire", Fraction(3, 10))}, "[-inf, 0.3000)"),
        # a lower limit fires below it: every fire value < limit <= every silent value
        ("METRIC009", {"a": ("silent", Fraction(0)), "b": ("silent", Fraction(1))}, "(-inf, 0.0000]"),
        ("METRIC009", {"a": ("fire", Fraction(1, 5)), "b": ("silent", Fraction(9, 10))}, "(0.2000, 0.9000]"),
        ("METRIC009", {"a": ("fire", Fraction(9, 10)), "b": ("silent", Fraction(1, 5))}, "none"),
        # a strict limit cannot tell equal values apart
        ("METRIC002", {"a": ("silent", Fraction(1, 2)), "b": ("fire", Fraction(1, 2))}, "none"),
    ],
)
def test_the_limits_the_labels_allow(rule: str, spec: dict[str, tuple[str, Fraction]], expected: str) -> None:
    entries, values = _labelled(spec)
    assert metric_corpus.consistent_limits(entries, rule, values, checked_only=False) == expected


def test_unknown_unassessed_and_presumed_labels_are_ignored_where_they_should_be() -> None:
    def entry(name: str, expect: str, basis: str) -> Any:
        return metric_corpus.Entry(name, "", "", {"*": {"expect": expect, "basis": basis, "why": "x"}})

    entries = [entry("a", "unknown", "checked"), entry("b", "unassessed", "none"), entry("c", "silent", "presumed")]
    values = {"a": Fraction(9, 10), "b": Fraction(9, 10), "c": Fraction(1, 10)}
    assert metric_corpus.consistent_limits(entries, "METRIC002", values, checked_only=False) == "[0.1000, +inf)"
    assert metric_corpus.consistent_limits(entries, "METRIC002", values, checked_only=True) == "[-inf, +inf)"


def test_a_label_on_a_file_below_the_sample_gate_is_not_a_value() -> None:
    """A file with no reading (gated out or empty) can neither fire nor be silent at any limit."""
    entries, values = _labelled({"a": ("fire", Fraction(9, 10)), "b": ("fire", Fraction(0))})
    del values["b"]
    assert metric_corpus.consistent_limits(entries, "METRIC002", values, checked_only=False) == "[-inf, 0.9000)"


def test_the_recorded_vectors_cover_every_entry_and_agree_with_the_recorded_findings() -> None:
    """The harness's model of each rule (reading, gate, limit) must give the findings the rules gave."""
    results = _results()
    entries = metric_corpus.load_manifest()
    assert set(results["vectors"]) == {entry.id for entry in entries}
    limits = metric_corpus.default_limits()
    for entry in entries:
        for rule in metric_corpus.RULES:
            value = metric_corpus.reading(rule, results["vectors"][entry.id], metric_corpus.sample_gate())
            fires = metric_corpus.would_fire(rule, value, limits[rule])
            assert fires == results["results"][entry.id][rule]["fires"], (entry.id, rule)


def test_a_vector_that_disagrees_with_the_forced_measurement_is_refused() -> None:
    forced = metric_corpus.parse_forced({"METRIC001": "6 of 10 classes lack a label (0.60 > 0.00)."})
    metric_corpus.check_vector("x.ttl", "METRIC001", _vector(class_label_coverage=(4, 10)), forced["METRIC001"])
    with pytest.raises(SystemExit, match=r"x\.ttl: METRIC001.*disagrees"):
        metric_corpus.check_vector("x.ttl", "METRIC001", _vector(class_label_coverage=(5, 10)), forced["METRIC001"])
    # A rule that was silent when forced must be at its boundary or over an empty population.
    silent = metric_corpus.parse_forced({})["METRIC001"]
    metric_corpus.check_vector("x.ttl", "METRIC001", _vector(class_label_coverage=(10, 10)), silent)
    metric_corpus.check_vector("x.ttl", "METRIC001", _vector(class_label_coverage=(0, 0)), silent)
    with pytest.raises(SystemExit, match="disagrees"):
        metric_corpus.check_vector("x.ttl", "METRIC001", _vector(class_label_coverage=(4, 10)), silent)


@pytest.mark.parametrize(
    "measurements",
    [
        [],  # a measurement the rules read is absent
        [{"id": "class_label_coverage", "definition_version": 1, "kind": "ratio", "reason": "could not be taken"}],
        [{"id": "class_label_coverage", "definition_version": 2, "kind": "ratio", "numerator": 1, "denominator": 1}],
    ],
)
def test_a_vector_that_is_absent_unavailable_or_of_another_version_is_refused(
    measurements: list[dict[str, Any]],
) -> None:
    with pytest.raises(SystemExit, match=r"x\.ttl"):
        metric_corpus.vector_of("x.ttl", {"measurements": measurements})


def test_the_vector_of_a_run_on_a_known_fixture(tmp_path: Path) -> None:
    path = tmp_path / "fixture.ttl"
    path.write_text(FIXTURE, encoding="utf-8")
    vector = metric_corpus._vector(path)
    assert vector["class_label_coverage"] == {"definition_version": 1, "numerator": 4, "denominator": 10}
    assert vector["class_fanout"] == {"definition_version": 1, "numerator": 3, "denominator": 1}
    assert vector["unresolved_imports"] == {"definition_version": 1, "value": 0}
    assert metric_corpus._vector(path) == vector  # deterministic


def test_the_generated_tables_are_deterministic_and_hold_every_rule() -> None:
    entries = metric_corpus.load_manifest()
    first = metric_corpus.render_calibration(entries, _results())
    assert first == metric_corpus.render_calibration(entries, json.loads(json.dumps(_results())))
    for heading in ("### Distributions", "### Limits the labels allow"):
        section = first.split(heading, 1)[1].split("###", 1)[0]
        for rule in metric_corpus.RULES:
            assert f"| {rule} |" in section, (heading, rule)


def test_the_calibration_page_shows_the_recorded_distributions() -> None:
    entries = metric_corpus.load_manifest()
    page = metric_corpus.CALIBRATION
    expected = metric_corpus.render_calibration(entries, _results())
    assert metric_corpus.generated_part(page, *metric_corpus.CALIBRATION_MARKERS) == expected, (
        "run: uv run python scripts/metric_corpus.py render"
    )


def test_the_calibration_page_states_what_it_cannot_decide() -> None:
    page = metric_corpus.CALIBRATION.read_text(encoding="utf-8")
    for text in ("recommend", "maintainer", "METRIC011", "dcam:domainIncludes", "#66", "proposed"):
        assert text in page
    for rule in metric_corpus.RULES:
        assert rule in page
