"""Targeted tests that pin behaviour the mutation run found unobserved (metrics rules)."""

# ruff: noqa: SLF001, PLR2004

from __future__ import annotations

from dataclasses import FrozenInstanceError, replace
from typing import Any

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rule_harness import BASE

from ontolint import engine
from ontolint.models import Finding
from ontolint.policy import Policy
from ontolint.rules import metrics


def _run(data: Graph, rule: str, **thresholds: Any) -> list[Finding]:
    policy = replace(Policy(), metric_min_sample=1, **thresholds)
    ctx = engine.build_context(data, None, policy)
    metrics.run(ctx)
    return [f for f in ctx.findings if f.rule == rule]


def _ex(name: str) -> URIRef:
    return URIRef(BASE + name)


def _cls(g: Graph, name: str) -> URIRef:
    g.add((_ex(name), RDF.type, OWL.Class))
    return _ex(name)


@pytest.mark.parametrize(
    ("iri", "expected"),
    [("http://a.test/b#c", "http://a.test/b#"), ("http://a.test/b", "http://a.test/"), ("/a", "/"), ("urn", "urn")],
)
def test_namespace_cuts_after_the_last_separator(iri: str, expected: str) -> None:
    assert metrics._namespace(URIRef(iri)) == expected


def test_hierarchy_is_immutable() -> None:
    h = metrics._Hierarchy({}, {})
    with pytest.raises(FrozenInstanceError):
        h.parents = {}  # type: ignore[misc]


def test_metric012_counts_only_class_definitions() -> None:
    g = Graph()
    c = _cls(g, "C")
    g.add((c, RDFS.comment, Literal("one two three four five")))
    p = _ex("p")
    g.add((p, RDF.type, OWL.ObjectProperty))
    g.add((p, RDFS.comment, Literal("short")))
    assert _run(g, "METRIC012") == []


def test_metric012_does_not_fire_when_mean_equals_threshold() -> None:
    g = Graph()
    g.add((_cls(g, "C"), RDFS.comment, Literal("one two three four")))
    assert _run(g, "METRIC012", metric_min_definition_words=4.0) == []
    assert len(_run(g, "METRIC012", metric_min_definition_words=4.5)) == 1


def test_metric010_does_not_fire_when_ratio_equals_limit() -> None:
    g = Graph()
    a = _cls(g, "A")
    g.add((a, RDFS.subClassOf, _ex("B")))
    g.add((a, RDFS.subClassOf, URIRef("http://elsewhere.test/X")))
    assert _run(g, "METRIC010", metric_max_foreign_reference_ratio=0.5) == []
    assert len(_run(g, "METRIC010", metric_max_foreign_reference_ratio=0.4)) == 1


def test_metric013_does_not_fire_when_ratio_equals_limit() -> None:
    g = Graph()
    g.add((_ex("s"), RDFS.label, Literal("x")))
    g.add((BNode(), RDFS.label, Literal("y")))
    assert _run(g, "METRIC013", metric_max_blank_node_ratio=0.5) == []
    assert len(_run(g, "METRIC013", metric_max_blank_node_ratio=0.4)) == 1


def test_metric001_counts_what_lex001_reports() -> None:
    g = Graph()
    for i in range(10):
        c = _cls(g, f"C{i}")
        if i < 3:
            g.add((c, RDFS.label, _ex("x")))  # an IRI is not a label
        elif i < 6:
            g.add((c, OWL.deprecated, Literal(True)))  # deprecated terms are exempt
        elif i < 8:
            g.add((c, RDFS.label, Literal("c")))
    (finding,) = _run(g, "METRIC001", metric_max_unlabelled_ratio=0.0)
    assert finding.message.startswith("5 of 10 classes lack a label")


def test_metric008_counts_what_owl005_and_owl006_report() -> None:
    g = Graph()
    substitutes = {
        0: (URIRef("https://schema.org/domainIncludes"), _ex("C")),
        1: (URIRef("http://purl.org/dc/dcam/rangeIncludes"), _ex("C")),
        2: (OWL.deprecated, Literal(True)),
        3: (RDFS.domain, _ex("C")),
    }
    for i in range(12):
        p = _ex(f"p{i}")
        g.add((p, RDF.type, OWL.ObjectProperty))
        if i in substitutes:
            g.add((p, *substitutes[i]))
    (finding,) = _run(g, "METRIC008", metric_max_unsigned_property_ratio=0.0)
    assert finding.message.startswith("8 of 12 object/datatype properties")


def test_metric005_counts_what_cls001_reports_on_the_kitchen_sink() -> None:
    from pathlib import Path  # noqa: PLC0415

    from ontolint.rules import classes  # noqa: PLC0415

    g = Graph()
    g.parse(Path(__file__).parent / "fixtures" / "kitchen_sink.ttl", format="turtle")
    policy = replace(Policy(), metric_max_orphan_ratio=0.0)
    ctx = engine.build_context(g, None, policy)
    classes.run(ctx)
    metrics.run(ctx)
    cls001 = [f for f in ctx.findings if f.rule == "CLS001"]
    (metric,) = [f for f in ctx.findings if f.rule == "METRIC005"]
    assert len(cls001) == 6
    assert metric.message.startswith("6 of 33 classes are orphans")


def test_metric006_and_007_count_relation_properties_only() -> None:
    g = Graph()
    for i in range(10):
        _cls(g, f"C{i}")
    for i in range(51):
        g.add((_ex(f"a{i}"), RDF.type, OWL.AnnotationProperty))
    assert _run(g, "METRIC007") == []
    (low,) = _run(g, "METRIC006")
    assert low.message == "0 properties for 10 classes (0.00 < 0.10)."
    # An annotation property that is also an object property is a relation; rdf:Property counts too.
    g.add((_ex("a0"), RDF.type, OWL.ObjectProperty))
    g.add((_ex("r"), RDF.type, RDF.Property))
    (still,) = _run(g, "METRIC006", metric_min_property_class_ratio=0.3)
    assert still.message.startswith("2 properties for 10 classes")


def _own_namespaces(n: int, *, header: bool) -> Graph:
    g = Graph()
    if header:
        g.add((URIRef("https://example.test/"), RDF.type, OWL.Ontology))
    for i in range(n):
        child, parent = URIRef(f"https://example.test/a#C{i}"), URIRef(f"https://example.test/b#D{i}")
        g.add((child, RDF.type, OWL.Class))
        g.add((parent, RDF.type, OWL.Class))
        g.add((child, RDFS.subClassOf, parent))
    return g


def _run_owned(g: Graph, base: str | None, **thresholds: Any) -> list[Finding]:
    policy = replace(Policy(), metric_min_sample=1, **thresholds)
    ctx = engine.build_context(g, base, policy)
    metrics.run(ctx)
    return [f for f in ctx.findings if f.rule == "METRIC010"]


def test_metric010_owned_namespaces_are_not_foreign() -> None:
    assert _run_owned(_own_namespaces(10, header=True), "https://example.test/") == []


def test_metric010_without_ownership_information_the_namespace_decides() -> None:
    (finding,) = _run_owned(_own_namespaces(10, header=False), None)
    assert finding.message.startswith("10 of 10 structural references")


def test_metric010_foreign_target_still_counts_when_ownership_is_known() -> None:
    g = _own_namespaces(10, header=True)
    for i in range(10):
        g.add((URIRef(f"https://example.test/a#C{i}"), RDFS.subClassOf, URIRef(f"https://elsewhere.test/x#E{i}")))
    (finding,) = _run_owned(g, "https://example.test/", metric_max_foreign_reference_ratio=0.4)
    assert finding.message.startswith("10 of 20 structural references")


def test_metric013_blank_structure_of_shapes_and_reification() -> None:
    from rdflib.namespace import SH  # noqa: PLC0415

    g = Graph()
    for i in range(10):
        shape = _ex(f"S{i}")
        g.add((shape, RDF.type, SH.NodeShape))
        member = BNode()
        g.add((member, SH["class"], _ex("A")))  # only an sh: statement marks the member
        g.add((shape, SH["not"], member))
        statement = BNode()
        g.add((statement, RDF.type, RDF.Statement))
        g.add((statement, RDF.subject, _ex("a")))
    assert _run(g, "METRIC013") == []
    # A blank node with a statement outside sh:/rdf: stays free.
    for _ in range(30):
        g.add((BNode(), RDFS.label, Literal("x")))
    (finding,) = _run(g, "METRIC013")
    assert finding.message.startswith("30 of 40 subjects are blank nodes")


@pytest.mark.parametrize(
    ("value", "limit", "shown"),
    [
        (0.5, 0.25, ("0.50", "0.25")),
        (10 / 33, 0.3, ("0.303", "0.300")),  # 2 decimals would print "0.30 > 0.30"
        (0.3001, 0.3, ("0.3001", "0.3000")),
        (0.300001, 0.3, ("0.300001", "0.300000")),
        (0.3, 0.3, ("0.300000", "0.300000")),  # equal never fires; nothing to widen
    ],
)
def test_value_and_limit_are_printed_apart(value: float, limit: float, shown: tuple[str, str]) -> None:
    assert metrics._vs(value, limit) == shown


def test_metric005_message_tells_a_ratio_just_over_its_limit_from_the_limit() -> None:
    g = Graph()
    for i in range(33):
        _cls(g, f"C{i}")
        if i >= 10:
            g.add((_ex(f"C{i}"), RDFS.subClassOf, _ex(f"C{(i % 23) + 10}")))
    (finding,) = _run(g, "METRIC005", metric_max_orphan_ratio=0.3)
    assert finding.message.endswith("(0.303 > 0.300).")
