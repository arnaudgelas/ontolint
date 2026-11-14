"""The measurement engine (``ontolint.rules.measurements``): the values, the cache, absence and failure.

The METRIC rules are thresholds over these measurements: a rule whose measurement is absent fails, and so the
run exits 2, which proves each rule reads its value from the engine.  The property tests are in
``test_measurements_properties.py``; every arithmetic and exclusion path also has an example here, since mutation
runs leave the slow tests out.
"""

# ruff: noqa: SLF001, PLR2004

from __future__ import annotations

import json
from collections import Counter
from dataclasses import FrozenInstanceError, replace
from pathlib import Path
from typing import Any

import pytest
from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDF, RDFS, SKOS
from rule_harness import BASE, graph

from ontolint import main
from ontolint.context import GraphContext
from ontolint.engine import build_context
from ontolint.graph import hierarchy_depths
from ontolint.policy import Policy
from ontolint.rules import measurements
from ontolint.rules import shapes as shapes_rules
from ontolint.rules.measurements import (
    Absent,
    Count,
    CountRatio,
    MeasurementUnavailable,
    TermRatio,
    TermValues,
    count,
    measure,
    owned_classes,
    owned_properties,
    ratio,
    require,
)
from ontolint.rules.runtime import RuleContext
from ontolint.rules.support import directed_edges

FIXTURES = Path(__file__).parent / "fixtures"
KITCHEN = FIXTURES / "kitchen_sink.ttl"
HEADER = "<https://example.test/onto> a owl:Ontology .\n"

# What the kitchen sink measures; the forced METRIC messages give the same numbers (missing = whole - covered).
KITCHEN_VALUES: dict[str, tuple[int, int] | int] = {
    "class_label_coverage": (32, 33),
    "class_definition_coverage": (6, 33),
    "property_documentation_coverage": (1, 14),
    "class_fanout": (15, 14),
    "orphan_classes": (6, 33),
    "relation_properties_per_class": (14, 33),
    "unsigned_properties": (3, 14),
    "label_language_coverage": (2, 46),
    "foreign_references": (0, 36),
    "unresolved_imports": 1,
    "definition_length": (7, 6),
    "blank_subjects": (0, 58),
}
METRIC_MEASUREMENTS = tuple(spec for spec in measurements.SPECS if spec.rules)


def _ctx(turtle: str, policy: Policy | None = None) -> RuleContext:
    return build_context(graph(turtle), None, policy or Policy())


def _value(ctx: RuleContext, measurement_id: str) -> tuple[int, int] | int:
    found = measure(ctx, measurement_id)
    return count(ctx, measurement_id) if isinstance(found, Count) else ratio(ctx, measurement_id)


def _names(terms: frozenset[Any]) -> list[str]:
    return sorted(str(term).removeprefix(BASE) for term in terms)


def _absent(monkeypatch: pytest.MonkeyPatch, measurement_id: str, reason: str = "x") -> None:
    """Make ``measurement_id`` absent through the catalogue the engine looks up at call time."""
    specs = tuple(
        replace(spec, compute=lambda _ctx: Absent(reason)) if spec.id == measurement_id else spec
        for spec in measurements.SPECS
    )
    monkeypatch.setattr(measurements, "SPECS", specs)


def _run(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, dict[str, Any], str]:
    code = main(argv)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def _statuses(report: dict[str, Any]) -> dict[str, tuple[str, str]]:
    return {x["rule"]: (x["status"], x["detail"]) for x in report["files"][0]["executions"]}


# --- the catalogue ------------------------------------------------------------------------------------------


def test_the_catalogue_has_unique_ids_and_starts_every_definition_at_version_1() -> None:
    ids = [spec.id for spec in measurements.SPECS]
    assert len(ids) == len(set(ids))
    assert {spec.version for spec in measurements.SPECS} == {1}


def test_every_metric_rule_reads_exactly_one_measurement() -> None:
    read = [rule for spec in measurements.SPECS for rule in spec.rules]
    assert sorted(read) == [f"METRIC{n:03d}" for n in range(1, 14)]


def test_kitchen_sink_values() -> None:
    ctx = build_context(Graph().parse(KITCHEN), None, Policy())
    assert {spec.id: _value(ctx, spec.id) for spec in METRIC_MEASUREMENTS} == KITCHEN_VALUES
    found = measure(ctx, "foreign_references")
    assert isinstance(found, CountRatio)
    assert found.by_namespace == ()


@pytest.mark.parametrize("kind", [TermRatio, TermValues, CountRatio, Count, Absent, measurements.MeasurementSpec])
def test_values_are_immutable(kind: type[Any]) -> None:
    value = {
        TermRatio: lambda: TermRatio(frozenset(), frozenset()),
        TermValues: lambda: TermValues({}),
        CountRatio: lambda: CountRatio(0, 0),
        Count: lambda: Count(0),
        Absent: lambda: Absent("r"),
        measurements.MeasurementSpec: lambda: measurements.SPECS[0],
    }[kind]()
    name = next(iter(vars(value)))
    with pytest.raises(FrozenInstanceError):
        setattr(value, name, None)


# --- the engine: cache, absence, failure ---------------------------------------------------------------------


def test_a_measurement_is_computed_once_per_context(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[RuleContext] = []

    def counted(ctx: RuleContext) -> Count:
        calls.append(ctx)
        return Count(7)

    specs = tuple(replace(s, compute=counted) if s.id == "unresolved_imports" else s for s in measurements.SPECS)
    monkeypatch.setattr(measurements, "SPECS", specs)
    ctx, other = _ctx(""), _ctx("")
    assert count(ctx, "unresolved_imports") == 7
    assert count(ctx, "unresolved_imports") == 7
    assert calls == [ctx]
    assert count(other, "unresolved_imports") == 7
    assert calls == [ctx, other]
    assert ctx.measured["unresolved_imports"] == Count(7)


def test_a_computation_that_raises_propagates_and_is_not_cached(monkeypatch: pytest.MonkeyPatch) -> None:
    outcomes: list[Exception | Count] = [ValueError("boom"), Count(1)]

    def flaky(_ctx: RuleContext) -> Count:
        outcome = outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    specs = tuple(replace(s, compute=flaky) if s.id == "unresolved_imports" else s for s in measurements.SPECS)
    monkeypatch.setattr(measurements, "SPECS", specs)
    ctx = _ctx("")
    with pytest.raises(ValueError, match="boom"):
        measure(ctx, "unresolved_imports")
    assert "unresolved_imports" not in ctx.measured
    assert count(ctx, "unresolved_imports") == 1


def test_an_absent_measurement_is_cached_and_required_values_raise(monkeypatch: pytest.MonkeyPatch) -> None:
    _absent(monkeypatch, "orphan_classes", "no reasoner ran")
    ctx = _ctx("")
    assert measure(ctx, "orphan_classes") == Absent("no reasoner ran")
    with pytest.raises(MeasurementUnavailable) as raised:
        require(ctx, "orphan_classes")
    assert str(raised.value) == "orphan_classes: no reasoner ran"
    assert (raised.value.measurement_id, raised.value.reason) == ("orphan_classes", "no reasoner ran")
    with pytest.raises(MeasurementUnavailable):
        ratio(ctx, "orphan_classes")
    assert ctx.measured["orphan_classes"] == Absent("no reasoner ran")


def test_the_accessors_refuse_the_wrong_kind_and_an_unknown_id() -> None:
    ctx = _ctx("")
    with pytest.raises(TypeError, match="unresolved_imports is a count, not a ratio"):
        ratio(ctx, "unresolved_imports")
    with pytest.raises(TypeError, match="orphan_classes is not a count"):
        count(ctx, "orphan_classes")
    with pytest.raises(KeyError):
        measure(ctx, "no_such_measurement")


def test_an_empty_graph_is_measured_as_empty_populations() -> None:
    ctx = _ctx("")
    assert {spec.id: _value(ctx, spec.id) for spec in METRIC_MEASUREMENTS} == {
        spec.id: 0 if spec.id == "unresolved_imports" else (0, 0) for spec in METRIC_MEASUREMENTS
    }


@pytest.mark.parametrize("spec", METRIC_MEASUREMENTS, ids=lambda spec: spec.id)
@pytest.mark.parametrize("sample", [None, 1000])
def test_a_metric_rule_fails_when_its_measurement_is_absent(
    spec: measurements.MeasurementSpec,
    sample: int | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # Above the population, the sample gate would silence the rule; an absent measurement still fails it.
    argv = [str(KITCHEN), "--format", "json", "--select", ",".join(spec.rules)]
    if sample is not None:
        config = tmp_path / "policy.json"
        config.write_text(json.dumps({"metric_min_sample": sample}), encoding="utf-8")
        argv += ["--config", str(config)]
    _absent(monkeypatch, spec.id)
    code, report, err = _run(argv, capsys)
    assert code == 2
    detail = f"MeasurementUnavailable: {spec.id}: x"
    assert _statuses(report) == dict.fromkeys(spec.rules, ("failed", detail))
    assert all(f"TOOL001: rule {rule} failed for " in err and detail in err for rule in spec.rules)


def test_a_metric_rule_executes_when_its_measurement_is_taken(capsys: pytest.CaptureFixture[str]) -> None:
    code, report, _err = _run([str(KITCHEN), "--format", "json", "--select", "METRIC"], capsys)
    assert code == 0
    assert {status for status, _detail in _statuses(report).values()} == {"executed"}


def test_a_failing_computation_fails_the_metric_rules_with_its_own_exception(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    def boom(_ctx: RuleContext, _term: URIRef) -> bool:
        raise ValueError("boom")

    monkeypatch.setattr(measurements, "is_unlabelled", boom)
    code, report, _err = _run([str(KITCHEN), "--format", "json", "--select", "METRIC,LEX001"], capsys)
    assert code == 2
    statuses = _statuses(report)
    assert statuses.pop("LEX001") == ("executed", "")
    assert set(statuses.values()) == {("failed", "ValueError: boom")}
    assert {f["rule"] for f in report["findings"]} == {"LEX001"}


# --- what each measurement counts ----------------------------------------------------------------------------


def test_label_coverage_counts_what_lex001_does_not_report() -> None:
    ctx = _ctx(
        "ex:A a owl:Class ; rdfs:label 'a' . ex:B a owl:Class ; owl:deprecated true ."
        " ex:C a owl:Class ; rdfs:label ex:iri . ex:D a owl:Class ; rdfs:label '' ."
        " ex:E a owl:Class ; skos:altLabel 'e' . ex:F a owl:Class ; ex:sublabel 'f' . ex:sublabel rdfs:subPropertyOf"
        " rdfs:label . ex:G a owl:Class ; owl:deprecated false ."
    )
    found = measure(ctx, "class_label_coverage")
    assert isinstance(found, TermRatio)
    # A deprecated class and an empty label count; an IRI label, an alternative label and deprecated false do not.
    assert _names(found.numerator) == ["A", "B", "D", "F"]
    assert _names(found.denominator) == ["A", "B", "C", "D", "E", "F", "G"]


def test_definition_coverage_follows_the_sub_property_closure_and_counts_any_value() -> None:
    ctx = _ctx(
        "ex:def1 rdfs:subPropertyOf skos:definition . ex:def2 rdfs:subPropertyOf ex:def1 ."
        " ex:A a owl:Class ; ex:def2 'deep' . ex:B a owl:Class ; skos:note 'a note' ."
        " ex:C a owl:Class ; rdfs:comment '' . ex:D a owl:Class ; skos:definition ex:iri ."
        " ex:E a owl:Class ; skos:scopeNote 'scope' ."
        " ex:p a owl:ObjectProperty ; rdfs:comment 'p' . ex:q a owl:AnnotationProperty ."
    )
    classes = measure(ctx, "class_definition_coverage")
    assert isinstance(classes, TermRatio)
    assert _names(classes.numerator) == ["A", "C", "D"]
    assert _names(classes.denominator) == ["A", "B", "C", "D", "E"]
    properties = measure(ctx, "property_documentation_coverage")
    assert isinstance(properties, TermRatio)
    assert (_names(properties.numerator), _names(properties.denominator)) == (["p"], ["p", "q"])


def test_extra_predicates_shape_the_coverage_populations() -> None:
    body = "ex:A a owl:Class ; ex:gloss 'g' ; ex:name 'n' ."
    plain = _ctx(body)
    configured = _ctx(
        body, replace(Policy(), extra_definition_predicates=(BASE + "gloss",), extra_label_predicates=(BASE + "name",))
    )
    assert ratio(plain, "class_definition_coverage") == (0, 1)
    assert ratio(plain, "class_label_coverage") == (0, 1)
    assert ratio(configured, "class_definition_coverage") == (1, 1)
    assert ratio(configured, "class_label_coverage") == (1, 1)


def test_owned_populations_apply_the_ownership_of_the_context() -> None:
    data = graph(HEADER + "ex:A a owl:Class . <https://other.example/X> a owl:Class . ex:p a owl:ObjectProperty .")
    # An is_local override keeps every class in ctx.classes; the measurements still count the owned ones only.
    context = GraphContext.build(data, lambda _node: True, restrict_to_local=True)
    ctx = RuleContext(data, None, Policy(), context)
    assert _names(ctx.classes) == ["A", "https://other.example/X"]
    assert owned_classes(ctx) == frozenset(c for c in ctx.classes if ctx.local(c))
    assert _names(owned_classes(ctx)) == ["A"]
    assert _names(owned_properties(ctx)) == ["p"]
    assert ratio(ctx, "class_label_coverage") == (0, 1)


def test_base_selects_the_owned_population() -> None:
    body = HEADER + "ex:A a owl:Class . <https://example.test/other#B> a owl:Class ."
    assert ratio(_ctx(body), "orphan_classes")[1] == 1
    assert ratio(_ctx(body, replace(Policy(), base="https://example.test/")), "orphan_classes")[1] == 2


def test_class_fanout_counts_direct_owned_subclasses_per_parent() -> None:
    ctx = _ctx(
        "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A , ex:B , [ a owl:Restriction ] ."
        " ex:C a owl:Class ; rdfs:subClassOf ex:A , <https://other.example/X> ."
        " ex:D a owl:Class ; rdfs:subClassOf ex:B ."
        " ex:Z rdfs:subClassOf ex:A ."
    )
    found = measure(ctx, "class_fanout")
    assert isinstance(found, TermValues)
    # A self-loop, a blank or external superclass and an undeclared subclass are not edges.
    assert {str(k).removeprefix(BASE): v for k, v in found.values.items()} == {"A": 2, "B": 1}
    assert ratio(ctx, "class_fanout") == (3, 2)


def test_orphan_classes_are_the_owned_classes_cls001_reports() -> None:
    ctx = _ctx(
        "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:C . ex:C a owl:Class ."
        " ex:D a owl:Class ; rdfs:subClassOf owl:Thing . ex:E a owl:Class ; owl:deprecated true ."
    )
    found = measure(ctx, "orphan_classes")
    assert isinstance(found, TermRatio)
    assert _names(found.numerator) == ["A"]
    assert len(found.denominator) == 5


def test_relation_properties_leave_out_annotation_only_properties() -> None:
    ctx = _ctx(
        "ex:A a owl:Class . ex:a a owl:AnnotationProperty . ex:b a owl:AnnotationProperty , owl:ObjectProperty ."
        " ex:c a rdf:Property . ex:d a owl:DatatypeProperty ."
    )
    found = measure(ctx, "relation_properties_per_class")
    assert isinstance(found, TermRatio)
    assert (_names(found.numerator), _names(found.denominator)) == (["b", "c", "d"], ["A"])


def test_unsigned_properties_are_those_owl005_and_owl006_both_report() -> None:
    ctx = _ctx(
        "ex:a a owl:ObjectProperty . ex:b a owl:ObjectProperty ; rdfs:domain ex:A . ex:c a owl:DatatypeProperty ;"
        " rdfs:range xsd:string . ex:d a owl:ObjectProperty ; owl:deprecated true . ex:e a owl:DatatypeProperty ."
        " ex:f a rdf:Property . ex:g a owl:AnnotationProperty . ex:h a owl:ObjectProperty ;"
        " <https://schema.org/domainIncludes> ex:A ."
    )
    found = measure(ctx, "unsigned_properties")
    assert isinstance(found, TermRatio)
    assert _names(found.numerator) == ["a", "e"]
    assert _names(found.denominator) == ["a", "b", "c", "d", "e", "h"]


def test_label_language_coverage_counts_labelled_owned_terms() -> None:
    ctx = _ctx(
        "ex:A a owl:Class ; rdfs:label 'a'@en , 'a' . ex:B a owl:Class ; rdfs:label 'b' . ex:C a owl:Class ."
        " ex:D a owl:Class ; rdfs:label ex:iri . ex:p a owl:ObjectProperty ; skos:prefLabel 'p'@fr ."
        " ex:E a owl:Class ; rdfs:label 'e'^^xsd:string . <https://other.example/X> rdfs:label 'x'@en ."
    )
    found = measure(ctx, "label_language_coverage")
    assert isinstance(found, TermRatio)
    assert (_names(found.numerator), _names(found.denominator)) == (["A", "p"], ["A", "B", "E", "p"])


def test_foreign_references_count_structural_references_and_split_the_foreign_ones_by_namespace() -> None:
    ctx = _ctx(
        HEADER + "ex:A a owl:Class ; rdfs:subClassOf ex:B , owl:Thing , [ a owl:Restriction ] ,"
        " <http://purl.obolibrary.org/obo/X_1> , <http://purl.obolibrary.org/obo/X_2> , <https://u:pw@ext.test/x#A> ."
        " ex:B a owl:Class . ex:C a owl:Class ; rdfs:subClassOf <https://v:pw2@ext.test/x#B> ;"
        " owl:equivalentClass <https://other.example/Y> ."
        " ex:p a owl:ObjectProperty ; rdfs:domain ex:A ; rdfs:range <https://other.example/Z> , xsd:string ."
        " <https://other.example/W> rdfs:subClassOf <https://far.example/V> ."
    )
    found = measure(ctx, "foreign_references")
    assert isinstance(found, CountRatio)
    assert (found.numerator, found.denominator) == (5, 7)
    assert found.by_namespace == (
        ("http://purl.obolibrary.org/obo/", 2),
        ("https://****@ext.test/x#", 2),
        ("https://other.example/", 1),
    )


def test_foreign_namespaces_are_sorted_whatever_the_order_of_the_triples() -> None:
    later, earlier = "ex:A rdfs:subClassOf <https://z.example/X> .", "ex:B rdfs:subClassOf <https://a.example/Y> ."
    for body in (f"{later} {earlier}", f"{earlier} {later}"):
        ctx = _ctx(HEADER + "ex:A a owl:Class . ex:B a owl:Class . " + body)
        found = measure(ctx, "foreign_references")
        assert isinstance(found, CountRatio)
        assert found.by_namespace == (("https://a.example/", 1), ("https://z.example/", 1)), body


def test_without_ownership_information_the_namespace_alone_makes_a_reference_foreign() -> None:
    ctx = _ctx("ex:A a owl:Class ; rdfs:subClassOf ex:B , <https://other.example/X> . ex:B a owl:Class .")
    assert ratio(ctx, "foreign_references") == (1, 2)


def test_unresolved_imports_are_distinct_iris_not_loaded_by_the_closure() -> None:
    body = HEADER + (
        "<https://example.test/onto> owl:imports <https://a.example/> , <https://b.example/> , [ ] , 'lit' ."
        " <https://example.test/other> a owl:Ontology ; owl:imports <https://a.example/> ."
    )
    assert count(_ctx(body), "unresolved_imports") == 2
    resolved = replace(Policy(), resolved_imports=frozenset({"https://b.example/"}))
    assert count(_ctx(body, resolved), "unresolved_imports") == 1


def test_definition_length_scores_the_longest_literal_definition_of_each_owned_class() -> None:
    ctx = _ctx(
        "ex:A a owl:Class ; rdfs:comment 'one two' , 'one two three' ; skos:definition 'x' ."
        " ex:B a owl:Class ; skos:definition ex:iri . ex:C a owl:Class ; rdfs:comment '' ."
        " ex:p a owl:ObjectProperty ; rdfs:comment 'one two three four five' ."
    )
    found = measure(ctx, "definition_length")
    assert isinstance(found, TermValues)
    assert {str(k).removeprefix(BASE): v for k, v in found.values.items()} == {"A": 3, "C": 0}
    assert ratio(ctx, "definition_length") == (3, 2)


def test_blank_subjects_leave_out_structural_blank_nodes() -> None:
    g = graph(
        "ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:B ] ."
        " [ ex:p ex:A ] . [ rdfs:label 'anonymous' ] . ex:L ex:list ( ex:A ex:B ) ."
    )
    ctx = build_context(g, None, Policy())
    blanks = {s for s in g.subjects() if isinstance(s, BNode) and not measurements._is_structural_blank(g, s)}
    assert len(blanks) == 2
    assert ratio(ctx, "blank_subjects") == (2, 4)
    g.add((BNode(), RDF.type, OWL.Axiom))
    assert ratio(build_context(g, None, Policy()), "blank_subjects") == (2, 4)


def test_coverage_measurements_never_count_more_than_their_population() -> None:
    ctx = build_context(Graph().parse(KITCHEN), None, Policy())
    for measurement_id in (
        "class_label_coverage",
        "class_definition_coverage",
        "property_documentation_coverage",
        "orphan_classes",
        "unsigned_properties",
        "label_language_coverage",
        "foreign_references",
        "blank_subjects",
    ):
        numerator, denominator = ratio(ctx, measurement_id)
        assert 0 <= numerator <= denominator, measurement_id
    edges, parents = ratio(ctx, "class_fanout")
    assert edges >= parents  # every parent has a child


def test_skos_concepts_are_not_in_any_term_population() -> None:
    ctx = _ctx("ex:k a skos:Concept ; skos:prefLabel 'k'@en .")
    assert ratio(ctx, "label_language_coverage") == (0, 0)
    assert ratio(ctx, "class_label_coverage") == (0, 0)
    assert SKOS.Concept in ctx.context.subjects_by_type


# --- the measurements no rule thresholds ---------------------------------------------------------------------


def _depths(turtle: str) -> dict[str, int]:
    found = measure(_ctx(turtle), "class_depth")
    assert isinstance(found, TermValues)
    return {str(k).removeprefix(BASE): v for k, v in found.values.items()}


def test_class_depth_counts_the_classes_on_the_longest_chain_from_the_top() -> None:
    chain = "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:C a owl:Class ; rdfs:subClassOf ex:B ."
    assert _depths(chain) == {"A": 1, "B": 2, "C": 3}
    # A diamond takes the longer way down; an external or blank superclass and a self-loop add no level.
    diamond = chain + (
        " ex:D a owl:Class ; rdfs:subClassOf ex:A , ex:C , ex:D , <https://other.example/X> , [ a owl:Restriction ] ."
    )
    assert _depths(diamond) == {"A": 1, "B": 2, "C": 3, "D": 4}
    assert _depths("ex:A a owl:Class ; rdfs:subClassOf ex:A .") == {"A": 1}
    assert _depths("") == {}


def test_class_depth_is_0_on_a_subclass_cycle_and_the_cycle_adds_no_level_below_it() -> None:
    cycle = "ex:A a owl:Class ; rdfs:subClassOf ex:B . ex:B a owl:Class ; rdfs:subClassOf ex:A ."
    assert _depths(cycle + " ex:C a owl:Class ; rdfs:subClassOf ex:A .") == {"A": 0, "B": 0, "C": 1}


def test_the_deepest_class_is_as_deep_as_the_highest_subtree_cls005_measures() -> None:
    data = Graph().parse(KITCHEN)
    ctx = build_context(data, None, Policy())
    found = measure(ctx, "class_depth")
    assert isinstance(found, TermValues)
    heights = hierarchy_depths(ctx.classes, directed_edges(data, RDFS.subClassOf, ctx.classes))
    assert max(found.values.values()) == max(heights.values()) == 6
    assert sorted(Counter(found.values.values()).items()) == [(0, 2), (1, 22), (2, 4), (3, 2), (4, 1), (5, 1), (6, 1)]


def test_hierarchy_components_join_owned_classes_through_subclass_edges_only() -> None:
    two_trees = (
        "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:C a owl:Class ; rdfs:subClassOf ex:A ."
        " ex:D a owl:Class . ex:E a owl:Class ; rdfs:subClassOf ex:D ."
    )
    assert count(_ctx(two_trees), "hierarchy_components") == 2
    # owl:Thing, an external superclass and other links connect nothing; an isolated class is a component.
    shared = (
        "owl:Thing a owl:Class . ex:A a owl:Class ; rdfs:subClassOf owl:Thing , <https://other.example/X> ;"
        " owl:equivalentClass ex:B . ex:B a owl:Class ; rdfs:subClassOf owl:Thing , <https://other.example/X> ."
    )
    assert count(_ctx(shared), "hierarchy_components") == 2
    assert count(_ctx("ex:A a owl:Class ; rdfs:subClassOf ex:A ."), "hierarchy_components") == 1
    assert count(_ctx(""), "hierarchy_components") == 0
    assert count(build_context(Graph().parse(KITCHEN), None, Policy()), "hierarchy_components") == 20


def test_shacl_class_target_coverage_is_absent_without_shapes_and_counts_reached_owned_classes() -> None:
    data = "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:C a owl:Class . ex:i a ex:C ."
    assert measure(_ctx(data), "shacl_class_target_coverage") == Absent("no SHACL shapes graph was supplied")
    empty = build_context(graph(data), Graph(), Policy())
    assert ratio(empty, "shacl_class_target_coverage") == (0, 3)
    shapes = graph("ex:S a sh:NodeShape ; sh:targetClass ex:A , <https://other.example/X> .")
    found = measure(build_context(graph(data), shapes, Policy()), "shacl_class_target_coverage")
    assert isinstance(found, TermRatio)
    # The target reaches A and its subclass B, and an external class, which is not in the population.
    assert (_names(found.numerator), _names(found.denominator)) == (["A", "B"], ["A", "B", "C"])


def test_shq006_reports_the_instantiated_owned_classes_the_shacl_coverage_leaves_out() -> None:
    shapes = Graph().parse(FIXTURES / "kitchen_shapes.ttl")
    ctx = build_context(Graph().parse(KITCHEN), shapes, Policy())
    found = measure(ctx, "shacl_class_target_coverage")
    assert isinstance(found, TermRatio)
    assert (len(found.numerator), len(found.denominator)) == (1, 33)
    with ctx.naming_shapes():
        shapes_rules.run(ctx)
    instantiated = {c for c in found.denominator if ctx.context.subjects_by_type.get(c)}
    assert {f.focus for f in ctx.findings if f.rule == "SHQ006"} == {str(c) for c in instantiated - found.numerator}
