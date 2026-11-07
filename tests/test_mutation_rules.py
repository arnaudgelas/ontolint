"""Targeted tests that pin behaviour the mutation run found unobserved (rules families)."""

from __future__ import annotations

from decimal import Decimal
from typing import Any

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding

EXTERNAL = "http://elsewhere.test/"


def _run(rule: str, data: Graph, shapes: Graph | None = None, **options: Any) -> list[Finding]:
    result = Linter(data, shapes, **options).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _ex(name: str) -> URIRef:
    return URIRef(BASE + name)


# --- IRI006 ----------------------------------------------------------------------------------


def test_iri006_flags_an_empty_query_marker() -> None:
    g = Graph()
    g.add((URIRef("https://a.test/term?"), RDF.type, OWL.Class))
    assert [f.rule for f in _run("IRI006", g)] == ["IRI006"]


# --- LEX011 / literal ordering ---------------------------------------------------------------


def test_untagged_and_tagged_labels_sort_together() -> None:
    data = graph('ex:A a owl:Class ; rdfs:label "a  b", "a  b"@en, "c  d"@fr, "e  f"^^xsd:token .')
    assert [f.rule for f in _run("LEX011", data)] == ["LEX011"]


# --- SHQ007 / _natural -----------------------------------------------------------------------


def test_cardinality_bounds_that_are_not_naturals_are_ignored() -> None:
    for low in ('"abc"', "true", "1.5", "ex:Low"):
        shapes = graph(f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:minCount {low} ; sh:maxCount 0 .")
        assert _run("SHQ007", graph("ex:A a owl:Class ."), shapes) == [], low


# --- SHQ018 / NaN ----------------------------------------------------------------------------


def test_decimal_nan_bound_is_ignored() -> None:
    shapes = graph("ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:maxInclusive 1 .")
    shapes.add((_ex("S"), URIRef("http://www.w3.org/ns/shacl#minInclusive"), Literal(Decimal("NaN"))))
    assert _run("SHQ018", graph("ex:A a owl:Class ."), shapes) == []


# --- SHQ021 / property-shape detection -------------------------------------------------------


def test_node_shape_that_is_also_a_property_shape_is_not_unused() -> None:
    for extra in ("a sh:PropertyShape", "sh:path ex:p"):
        shapes = graph(f"ex:S a sh:NodeShape ; {extra} .")
        assert _run("SHQ021", graph(""), shapes) == [], extra


def test_untyped_shape_is_not_an_unused_node_shape() -> None:
    shapes = graph("ex:S sh:minCount 1 .")
    assert _run("SHQ021", graph(""), shapes) == []


# --- SKOS: scheme membership from non-IRI nodes ----------------------------------------------


def _shared_notation(body: str) -> list[Finding]:
    return _run("SKOS020", graph(body))


def test_blank_scheme_does_not_group_concepts() -> None:
    body = 'ex:A skos:inScheme _:s ; skos:notation "1" . ex:B skos:inScheme _:s ; skos:notation "1" .'
    assert _shared_notation(body) == []
    body = '_:s skos:hasTopConcept ex:A, ex:B . ex:A skos:notation "1" . ex:B skos:notation "1" .'
    assert _shared_notation(body) == []


def test_blank_concept_does_not_join_a_scheme() -> None:
    body = '_:c skos:inScheme ex:S ; skos:notation "1" . ex:A skos:inScheme ex:S ; skos:notation "1" .'
    assert _shared_notation(body) == []
    body = 'ex:S skos:hasTopConcept _:c, ex:A . _:c skos:notation "1" . ex:A skos:notation "1" .'
    assert _shared_notation(body) == []
    assert _run("SKOS015", graph("ex:S a skos:ConceptScheme . _:c skos:inScheme ex:S .")) == []


# --- SKOS: one local end is enough -----------------------------------------------------------

_OUT = f"<{EXTERNAL}x>"


def test_skos009_needs_only_one_local_end() -> None:
    data = graph(f"ex:a skos:related {_OUT} ; skos:broader {_OUT} .")
    assert [f.rule for f in _run("SKOS009", data, base=BASE)] == ["SKOS009"]


def test_skos012_needs_only_one_local_end() -> None:
    data = graph(f"ex:a skos:exactMatch {_OUT} ; skos:broadMatch {_OUT} .")
    assert [f.rule for f in _run("SKOS012", data, base=BASE)] == ["SKOS012"]


def test_skos011_needs_only_one_local_end() -> None:
    data = graph(f"ex:a skos:inScheme ex:s ; skos:exactMatch {_OUT} . {_OUT} skos:inScheme ex:s .")
    assert [f.rule for f in _run("SKOS011", data, base=BASE)] == ["SKOS011"]


def test_skos019_needs_only_one_local_end() -> None:
    data = graph(f"ex:a skos:inScheme ex:s ; skos:broader {_OUT} . {_OUT} skos:inScheme ex:t .")
    assert [f.rule for f in _run("SKOS019", data, base=BASE)] == ["SKOS019"]


def test_skos018_ignores_non_iri_parents() -> None:
    data = graph("ex:A skos:broader ex:B, _:x . ex:B skos:broader _:x .")
    assert _run("SKOS018", data) == []
    data = graph('ex:A skos:broader ex:B, "x" . ex:B skos:broader "x" .')
    assert _run("SKOS018", data) == []


def test_skos021_message_names_the_language() -> None:
    data = graph(
        'ex:A a skos:Concept ; skos:inScheme ex:S ; skos:prefLabel "Same" . '
        'ex:B a skos:Concept ; skos:inScheme ex:S ; skos:prefLabel "Same" . '
        'ex:C a skos:Concept ; skos:inScheme ex:S ; skos:prefLabel "Other"@en . '
        'ex:D a skos:Concept ; skos:inScheme ex:S ; skos:prefLabel "Other"@en .'
    )
    messages = sorted({f.message.split(" is shared")[0] for f in _run("SKOS021", data)})
    assert messages == ["skos:prefLabel 'other' (en)", "skos:prefLabel 'same' (no language)"]


def test_literals_order_plain_before_typed_within_a_language() -> None:
    data = graph('ex:A a owl:Class ; rdfs:label "z."^^xsd:token, "y." .')
    assert [f.message for f in _run("LEX012", data)] == [
        "Label 'y.' ends with punctuation.",
        "Label 'z.' ends with punctuation.",
    ]
