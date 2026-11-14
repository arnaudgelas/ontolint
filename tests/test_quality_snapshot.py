"""The quality snapshot (:mod:`ontolint.quality`): what a run records, the file it is written to, what is refused.

The file format is pinned here as exact documents, so a change to it shows as a change to a test and needs a
new ``SNAPSHOT_VERSION``.  ``docs/quality.md`` documents the same schema.
"""

from __future__ import annotations

import contextlib
import copy
import json
from dataclasses import replace
from pathlib import Path
from typing import Any

import pytest
from hypothesis import given
from hypothesis import strategies as st
from rdflib import Graph, URIRef
from rule_harness import graph

from ontolint.engine import build_context
from ontolint.models import Measurement, MeasurementKind
from ontolint.policy import Policy
from ontolint.quality import (
    SNAPSHOT_FORMAT,
    SNAPSHOT_VERSION,
    Coverage,
    Entry,
    Shaping,
    Snapshot,
    SnapshotError,
    build,
    dumps,
    loads,
)
from ontolint.rules import measurements
from ontolint.rules.measurements import TermRatio

FIXTURES = Path(__file__).parent / "fixtures"
Q = "https://example.test/q#"


def snapshot_of(turtle: str, policy: Policy | None = None) -> Snapshot:
    return build(build_context(graph(turtle), None, policy or Policy()))


def fixture(name: str) -> Graph:
    return Graph().parse(FIXTURES / "quality" / name, format="turtle")


def fixture_snapshot(name: str) -> Snapshot:
    return build(build_context(fixture(name), None, Policy()))


def entry(snap: Snapshot, measurement_id: str) -> Entry:
    return next(e for e in snap.entries if e.measurement.id == measurement_id)


# --- what a run records ---------------------------------------------------------------------------------------


def test_a_snapshot_holds_every_measurement_of_the_catalogue_in_its_order() -> None:
    snap = fixture_snapshot("before.ttl")
    assert [e.measurement.id for e in snap.entries] == [spec.id for spec in measurements.SPECS]
    assert [e.measurement for e in snap.entries] == list(
        measurements.publish(
            build_context(__import__("rdflib").Graph().parse(FIXTURES / "quality" / "before.ttl"), None, Policy())
        )
    )


def test_a_coverage_measure_keeps_the_sorted_iris_of_both_sets() -> None:
    coverage = entry(fixture_snapshot("before.ttl"), "class_definition_coverage").coverage
    assert coverage is not None
    assert coverage.better == "higher"
    assert coverage.numerator == tuple(f"{Q}{n}" for n in "ABC")
    assert coverage.denominator == tuple(f"{Q}{n}" for n in "ABCDE")


def test_the_counts_of_a_coverage_measure_are_those_of_its_sets() -> None:
    for e in fixture_snapshot("before.ttl").entries:
        if e.coverage is not None:
            assert (e.measurement.numerator, e.measurement.denominator) == (
                len(e.coverage.numerator),
                len(e.coverage.denominator),
            )


def test_a_measurement_with_other_than_a_numerator_within_its_denominator_keeps_counts_only() -> None:
    snap = fixture_snapshot("before.ttl")
    for measurement_id in ("relation_properties_per_class", "class_fanout", "definition_length", "class_depth"):
        assert entry(snap, measurement_id).coverage is None


def test_the_measures_that_say_what_is_better_are_exactly_the_coverage_ones() -> None:
    better = {spec.id: spec.better for spec in measurements.SPECS if spec.better}
    assert better == {
        "class_label_coverage": "higher",
        "class_definition_coverage": "higher",
        "property_documentation_coverage": "higher",
        "orphan_classes": "lower",
        "unsigned_properties": "lower",
        "label_language_coverage": "higher",
        "cyclic_classes": "lower",
        "shacl_class_target_coverage": "higher",
    }


def test_the_numerator_of_every_coverage_measure_is_within_its_denominator() -> None:
    kitchen = Graph().parse(FIXTURES / "kitchen_sink.ttl", format="turtle")
    ctx = build_context(kitchen, Graph(), Policy())
    for spec, value in measurements.taken(ctx):
        if spec.better:
            assert isinstance(value, TermRatio), spec.id
            assert value.numerator <= value.denominator, spec.id
        elif isinstance(value, TermRatio):
            # The one ratio of two kinds of term: properties over classes.
            assert spec.id == "relation_properties_per_class"


def test_a_measure_that_could_not_be_taken_is_recorded_with_its_reason() -> None:
    e = entry(fixture_snapshot("before.ttl"), "shacl_class_target_coverage")
    assert e.coverage is None and e.measurement.reason == "no SHACL shapes graph was supplied"


def test_the_policy_that_shaped_the_populations_is_recorded_sorted_and_masked() -> None:
    policy = Policy(
        base="https://user:secret@example.test/q#",
        extra_label_predicates=("https://example.test/z", "https://example.test/a"),
        extra_definition_predicates=("https://example.test/d",),
        resolved_imports=frozenset({"https://example.test/i2", "https://example.test/i1"}),
    )
    shaping = snapshot_of("", policy).shaping
    assert "secret" not in str(shaping) and shaping.base is not None and shaping.base.startswith("https://")
    assert shaping.extra_label_predicates == ("https://example.test/a", "https://example.test/z")
    assert shaping.extra_definition_predicates == ("https://example.test/d",)
    assert shaping.imports == ("https://example.test/i1", "https://example.test/i2")
    assert snapshot_of("").shaping == Shaping()


def test_term_iris_that_differ_only_in_their_userinfo_are_one_term() -> None:
    turtle = """
    <https://example.test/q> a owl:Ontology .
    <https://a:x@example.test/q#T> a owl:Class ; rdfs:label "T" .
    <https://b:y@example.test/q#T> a owl:Class ; rdfs:label "T" .
    """
    coverage = entry(snapshot_of(turtle), "class_label_coverage")
    assert coverage.coverage is not None
    assert len(coverage.coverage.denominator) == 1 and coverage.measurement.denominator == 1
    text = dumps(snapshot_of(turtle))
    assert "a:x" not in text and "b:y" not in text and "https://****@example.test/q#T" in text


def test_an_empty_ontology_has_a_snapshot_of_empty_sets() -> None:
    e = entry(snapshot_of(""), "class_label_coverage")
    assert e.coverage == Coverage("higher", (), ()) and (e.measurement.numerator, e.measurement.denominator) == (0, 0)


def test_a_coverage_numerator_outside_its_denominator_is_refused_at_build(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = measurements.spec_of("class_label_coverage")
    wrong = TermRatio(frozenset({URIRef(Q + "A")}), frozenset())
    monkeypatch.setattr(measurements, "SPECS", (replace(spec, compute=lambda ctx: wrong),))
    with pytest.raises(SnapshotError, match="among the denominator"):
        snapshot_of("")


# --- the file ---------------------------------------------------------------------------------------------------


def test_a_snapshot_round_trips() -> None:
    snap = fixture_snapshot("before.ttl")
    assert loads(dumps(snap)) == snap
    assert dumps(loads(dumps(snap))) == dumps(snap)


def test_a_snapshot_is_the_same_text_every_time() -> None:
    assert dumps(fixture_snapshot("before.ttl")) == dumps(fixture_snapshot("before.ttl"))


def test_the_file_is_utf_8_json_with_one_iri_per_line_and_a_final_newline() -> None:
    text = dumps(fixture_snapshot("before.ttl"))
    assert text.endswith("}\n") and not text.endswith("\n\n")
    assert f'      "{Q}A",\n' in text
    document = json.loads(text)
    assert list(document) == ["format", "version", "policy", "measurements"]
    assert document["format"] == SNAPSHOT_FORMAT == "ontolint-quality-snapshot"
    assert document["version"] == SNAPSHOT_VERSION == 1


def test_the_document_of_a_small_snapshot_is_exactly_this() -> None:
    snap = Snapshot(
        Shaping(base="https://example.test/q#", imports=("https://example.test/i",)),
        (
            Entry(
                Measurement("c", 1, MeasurementKind.RATIO, "owned_classes", numerator=1, denominator=2),
                Coverage("lower", (Q + "A",), (Q + "A", Q + "B")),
            ),
            Entry(Measurement("n", 2, MeasurementKind.COUNT, "graph", value=3)),
            Entry(
                Measurement(
                    "f",
                    1,
                    MeasurementKind.RATIO,
                    "structural_references",
                    numerator=1,
                    denominator=4,
                    by_namespace=(("https://x.test/", 1),),
                )
            ),
            Entry(Measurement("h", 1, MeasurementKind.HISTOGRAM, "acyclic_owned_classes", buckets=((1, 4),))),
            Entry(
                Measurement("u", 1, MeasurementKind.RATIO, "owned_classes", reason="no SHACL shapes graph was supplied")
            ),
        ),
    )
    assert json.loads(dumps(snap)) == {
        "format": "ontolint-quality-snapshot",
        "version": 1,
        "policy": {
            "base": "https://example.test/q#",
            "extra_label_predicates": [],
            "extra_definition_predicates": [],
            "imports": ["https://example.test/i"],
        },
        "measurements": [
            {
                "id": "c",
                "definition_version": 1,
                "kind": "ratio",
                "population": "owned_classes",
                "numerator": 1,
                "denominator": 2,
                "better": "lower",
                "numerator_terms": [Q + "A"],
                "denominator_terms": [Q + "A", Q + "B"],
            },
            {"id": "n", "definition_version": 2, "kind": "count", "population": "graph", "value": 3},
            {
                "id": "f",
                "definition_version": 1,
                "kind": "ratio",
                "population": "structural_references",
                "numerator": 1,
                "denominator": 4,
                "by_namespace": [{"namespace": "https://x.test/", "count": 1}],
            },
            {
                "id": "h",
                "definition_version": 1,
                "kind": "histogram",
                "population": "acyclic_owned_classes",
                "buckets": [{"value": 1, "count": 4}],
            },
            {
                "id": "u",
                "definition_version": 1,
                "kind": "ratio",
                "population": "owned_classes",
                "reason": "no SHACL shapes graph was supplied",
            },
        ],
    }
    assert loads(dumps(snap)) == snap


@given(
    names=st.sets(st.sampled_from("ABCDEFGH")),
    pick=st.lists(st.booleans(), min_size=8, max_size=8),
    better=st.sampled_from(("higher", "lower")),
)
def test_any_coverage_snapshot_round_trips(names: set[str], pick: list[bool], better: str) -> None:
    d = tuple(sorted(Q + n for n in names))
    n = tuple(t for t, keep in zip(d, pick, strict=False) if keep)
    e = Entry(
        Measurement("m", 1, MeasurementKind.RATIO, "p", numerator=len(n), denominator=len(d)), Coverage(better, n, d)
    )
    snap = Snapshot(Shaping(), (e,))
    assert loads(dumps(snap)) == snap


def good() -> dict[str, Any]:
    return json.loads(dumps(fixture_snapshot("before.ttl")))  # type: ignore[no-any-return]


def mutated(change: Any) -> str:
    document = good()
    change(document)
    return json.dumps(document)


def first(document: dict[str, Any], measurement_id: str) -> dict[str, Any]:
    return next(m for m in document["measurements"] if m["id"] == measurement_id)  # type: ignore[no-any-return]


REFUSED = {
    "not json": ("{", "not JSON"),
    "empty": ("", "not JSON"),
    "a list": ("[]", "a snapshot is a JSON object"),
    "a baseline file": (json.dumps({"version": 2, "fingerprints": []}), "has the keys"),
    "another format": (mutated(lambda d: d.update(format="ontolint-baseline")), "not a quality snapshot"),
    "a later version": (mutated(lambda d: d.update(version=2)), "version 2 is not supported"),
    "a boolean version": (mutated(lambda d: d.update(version=True)), "is not supported"),
    "a text version": (mutated(lambda d: d.update(version="1")), "is not supported"),
    "an extra top key": (mutated(lambda d: d.update(generated="today")), "has the keys"),
    "a missing policy": (mutated(lambda d: d.pop("policy")), "has the keys"),
    "an unknown policy key": (mutated(lambda d: d["policy"].update(threshold=1)), "the policy has the keys"),
    "a policy base of a number": (mutated(lambda d: d["policy"].update(base=1)), "base is text or null"),
    "a policy list of numbers": (mutated(lambda d: d["policy"].update(imports=[1])), "hold text"),
    "measurements not a list": (mutated(lambda d: d.update(measurements={})), "is a JSON array"),
    "a measurement that is not an object": (mutated(lambda d: d["measurements"].append(1)), "is a JSON object"),
    "an unknown kind": (mutated(lambda d: first(d, "class_depth").update(kind="gauge")), "has a kind of"),
    "an unknown measurement key": (mutated(lambda d: first(d, "class_depth").update(mean=2)), "has no key"),
    "a count with a numerator": (mutated(lambda d: first(d, "unresolved_imports").update(numerator=1)), "has no key"),
    "a ratio without a denominator": (mutated(lambda d: first(d, "orphan_classes").pop("denominator")), "cannot have"),
    "a float count": (mutated(lambda d: first(d, "class_fanout").update(numerator=1.5)), "integers"),
    "a missing id": (mutated(lambda d: first(d, "class_depth").pop("id")), "has an id"),
    "a definition version of zero": (
        mutated(lambda d: first(d, "class_depth").update(definition_version=0)),
        "positive integer",
    ),
    "a reason that is not text": (
        mutated(lambda d: first(d, "shacl_class_target_coverage").update(reason=3)),
        "a reason is text",
    ),
    "a duplicate measurement": (mutated(lambda d: d["measurements"].append(d["measurements"][0])), "appears once"),
    "descending buckets": (
        mutated(lambda d: first(d, "class_depth").update(buckets=[{"value": 2, "count": 1}, {"value": 1, "count": 1}])),
        "ascending",
    ),
    "a bucket of another shape": (
        mutated(lambda d: first(d, "class_depth").update(buckets=[{"value": 1}])),
        "a bucket has",
    ),
    "terms without better": (
        mutated(lambda d: first(d, "class_label_coverage").pop("better")),
        "go together",
    ),
    "better of another reading": (
        mutated(lambda d: first(d, "class_label_coverage").update(better="up")),
        "higher or lower",
    ),
    "a count that is not the terms": (
        mutated(lambda d: first(d, "class_label_coverage").update(numerator=1)),
        "the counts are those",
    ),
    "unsorted terms": (
        mutated(lambda d: first(d, "class_label_coverage")["denominator_terms"].reverse()),
        "sorted, each once",
    ),
    "a repeated term": (
        mutated(lambda d: first(d, "class_label_coverage").update(numerator_terms=[Q + "A", Q + "A"], numerator=2)),
        "sorted, each once",
    ),
    "terms that are not text": (
        mutated(lambda d: first(d, "class_label_coverage").update(numerator_terms=[1], numerator=1)),
        "sorted, each once",
    ),
    "a numerator outside the denominator": (
        mutated(lambda d: first(d, "class_label_coverage").update(numerator_terms=[Q + "Z"], numerator=1)),
        "among the denominator",
    ),
    "terms of a count": (
        mutated(
            lambda d: first(d, "unresolved_imports").update(better="higher", numerator_terms=[], denominator_terms=[])
        ),
        "only a ratio that was taken",
    ),
    "terms of a measurement not taken": (
        mutated(
            lambda d: first(d, "shacl_class_target_coverage").update(
                better="higher", numerator_terms=[], denominator_terms=[]
            )
        ),
        "only a ratio that was taken",
    ),
}


@pytest.mark.parametrize("text", [pair[0] for pair in REFUSED.values()], ids=list(REFUSED))
def test_an_unusable_snapshot_is_refused_with_a_snapshot_error(text: str) -> None:
    expected = REFUSED[next(k for k, v in REFUSED.items() if v[0] == text)][1]
    with pytest.raises(SnapshotError, match=expected):
        loads(text)


def test_a_snapshot_nested_too_deeply_is_refused_and_does_not_crash() -> None:
    with pytest.raises(SnapshotError):
        loads("[" * 100_000)


def test_the_good_document_is_not_refused() -> None:
    assert loads(json.dumps(good())) == fixture_snapshot("before.ttl")
    assert copy.deepcopy(good()) == good()


JSON = st.recursive(
    st.none() | st.booleans() | st.integers(-3, 3) | st.floats() | st.text(max_size=4),
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(st.text(max_size=6), inner, max_size=3),
    max_leaves=12,
)


def paths(node: Any, prefix: tuple[Any, ...] = ()) -> list[tuple[Any, ...]]:
    """Every place of a JSON document, as the keys and indexes leading to it."""
    if isinstance(node, dict):
        return [prefix] + [p for k, v in node.items() for p in paths(v, (*prefix, k))]
    if isinstance(node, list):
        return [prefix] + [p for i, v in enumerate(node) for p in paths(v, (*prefix, i))]
    return [prefix]


GOOD_PATHS = [p for p in paths(good()) if p]


@given(value=JSON)
def test_loading_arbitrary_json_gives_a_snapshot_or_a_snapshot_error(value: Any) -> None:
    with contextlib.suppress(SnapshotError):
        loads(json.dumps(value))


@given(place=st.sampled_from(GOOD_PATHS), value=JSON)
def test_a_good_snapshot_with_one_place_replaced_is_a_snapshot_or_a_snapshot_error(
    place: tuple[Any, ...], value: Any
) -> None:
    document = good()
    parent = document
    for step in place[:-1]:
        parent = parent[step]
    parent[place[-1]] = value
    try:
        snap = loads(json.dumps(document))
    except SnapshotError:
        return
    assert loads(dumps(snap)) == snap  # whatever is accepted is a snapshot that round-trips
