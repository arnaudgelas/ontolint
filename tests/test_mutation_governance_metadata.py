"""Targeted tests pinning exact messages, boundaries and both operands of every condition (governance_metadata)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding

TIED = 2  # Terms flagged when exactly half of four or three of five carry the annotation.
_EXTRA = (
    "@prefix obo: <http://purl.obolibrary.org/obo/> .\n"
    "@prefix pav: <http://purl.org/pav/> .\n"
    "@prefix vs: <http://www.w3.org/2003/06/sw-vocab-status/ns#> .\n"
)


def _run(rule: str, data: Graph, base: str | None = None) -> list[Finding]:
    result = Linter(data, base=base).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _g(turtle: str) -> Graph:
    return graph(_EXTRA + turtle)


def _classes(count: int, annotated: int, annotation: str) -> Graph:
    lines = [
        f"ex:T{i} a owl:Class ; {annotation} ." if i < annotated else f"ex:T{i} a owl:Class ." for i in range(count)
    ]
    return _g("\n".join(lines))


def test_gov004_message_and_focus_once_per_ontology() -> None:
    found = _run("GOV004", _g("ex:b a owl:Ontology . ex:a a owl:Ontology ."))
    assert [(f.focus, f.message) for f in found] == [
        (BASE + "a", "Ontology names no contact, publisher or maintainer."),
        (BASE + "b", "Ontology names no contact, publisher or maintainer."),
    ]


def test_gov004_contact_on_another_ontology_does_not_count() -> None:
    found = _run("GOV004", _g('ex:a a owl:Ontology ; dcterms:publisher "P" . ex:b a owl:Ontology .'))
    assert [f.focus for f in found] == [BASE + "b"]


def test_gov004_contact_on_a_term_does_not_count() -> None:
    assert len(_run("GOV004", _g('ex:a a owl:Ontology . ex:A a owl:Class ; dcterms:publisher "P" .'))) == 1


def test_gov008_message_and_each_operand() -> None:
    found = _run("GOV008", _g("ex:A a owl:Class ; owl:deprecated true ."))
    assert [(f.focus, f.message) for f in found] == [
        (BASE + "A", "Deprecated term has neither a replacement nor an obsolescence reason.")
    ]
    assert _run("GOV008", _g("ex:A a owl:Class ; owl:deprecated true ; dcterms:isReplacedBy ex:B .")) == []
    assert _run("GOV008", _g("ex:A a owl:Class ; owl:deprecated true ; rdfs:comment 'r' .")) == []
    assert _run("GOV008", _g("ex:A a owl:Class ; dcterms:isReplacedBy ex:B .")) == []


def test_gov008_ignores_non_deprecated_terms_without_annotations() -> None:
    assert _run("GOV008", _g("ex:A a owl:Class .")) == []


@pytest.mark.parametrize(
    ("rule", "annotation", "what"),
    [
        ("GOV009", 'dcterms:creator "A"', "creator or contributor attribution"),
        ("GOV010", 'dcterms:modified "2024-01-01"', "creation or modification date"),
        ("GOV012", "vs:term_status 'stable'", "status"),
    ],
)
def test_coverage_rules_message_and_boundaries(rule: str, annotation: str, what: str) -> None:
    found = _run(rule, _classes(4, 3, annotation))
    assert [(f.focus, f.message) for f in found] == [(BASE + "T3", f"Term has no {what}, though most local terms do.")]
    assert len(_run(rule, _classes(4, 2, annotation))) == TIED  # exactly half is still a convention
    assert _run(rule, _classes(4, 1, annotation)) == []
    assert _run(rule, _classes(3, 2, annotation)) == []  # below the minimum sample
    assert len(_run(rule, _classes(5, 4, annotation))) == 1
    assert _run(rule, _classes(5, 2, annotation)) == []  # 2 of 5 is under half
    assert len(_run(rule, _classes(5, 3, annotation))) == TIED


@pytest.mark.parametrize(
    ("rule", "annotations"),
    [
        ("GOV009", ["dcterms:creator", "dcterms:contributor", "dc:creator", "dc:contributor", "pav:createdBy"]),
        ("GOV010", ["dcterms:created", "dcterms:modified", "dcterms:issued", "dcterms:date", "dc:date"]),
        ("GOV012", ["vs:term_status", "obo:IAO_0000114", "adms:status", "bibo:status"]),
    ],
)
def test_every_accepted_predicate_counts_as_covered(rule: str, annotations: list[str]) -> None:
    prefixes = (
        "@prefix dc: <http://purl.org/dc/elements/1.1/> .\n"
        "@prefix adms: <http://www.w3.org/ns/adms#> .\n"
        "@prefix bibo: <http://purl.org/ontology/bibo/> .\n"
    )
    for predicate in annotations:
        data = _g(
            prefixes + "\n".join(f'ex:T{i} a owl:Class ; {predicate} "x" .' for i in range(4)) + "\nex:U a owl:Class ."
        )
        assert [f.focus for f in _run(rule, data)] == [BASE + "U"], predicate


def test_coverage_rules_skip_deprecated_and_foreign_terms() -> None:
    data = _classes(4, 4, 'dcterms:creator "A"')
    data += _g("ex:Old a owl:Class ; owl:deprecated true . ex:Z a owl:Class .")
    assert [f.focus for f in _run("GOV009", data)] == [BASE + "Z"]
    # Foreign terms are outside the base: they neither count towards the sample nor get flagged.
    foreign = _g("<https://other.test/X> a owl:Class . <https://other.test/Y> a owl:Class .")
    assert _run("GOV009", _classes(4, 4, 'dcterms:creator "A"') + foreign, base=BASE) == []
    assert _run("GOV009", _classes(3, 3, 'dcterms:creator "A"') + foreign, base=BASE) == []


def test_coverage_deprecated_terms_do_not_count_towards_the_sample() -> None:
    data = _classes(3, 2, 'dcterms:creator "A"') + _g("ex:Old a owl:Class ; owl:deprecated true .")
    assert _run("GOV009", data) == []  # three live terms only


def test_gov011_message_and_operands() -> None:
    found = _run("GOV011", _g('ex:o a owl:Ontology ; owl:versionInfo "1" .'))
    assert [(f.focus, f.message) for f in found] == [(BASE + "o", "Versioned ontology records no change history.")]
    assert len(_run("GOV011", _g("ex:o a owl:Ontology ; owl:versionIRI ex:o1 ."))) == 1
    assert _run("GOV011", _g("ex:o a owl:Ontology . ex:A a owl:Class .")) == []
    assert _run("GOV011", _g('ex:o a owl:Ontology ; owl:versionInfo "1" . ex:A skos:changeNote "c" .')) == []


def test_gov011_multiple_ontologies_each_reported() -> None:
    data = _g(
        'ex:a a owl:Ontology ; owl:versionInfo "1" . ex:b a owl:Ontology ; owl:versionInfo "2" . ex:c a owl:Ontology .'
    )
    assert [f.focus for f in _run("GOV011", data)] == [BASE + "a", BASE + "b"]


def test_gov017_message_and_operands() -> None:
    found = _run("GOV017", _g('ex:o a owl:Ontology ; owl:versionInfo "1" .'))
    assert [(f.focus, f.message) for f in found] == [
        (BASE + "o", "Versioned ontology records no review or approval metadata.")
    ]
    assert len(_run("GOV017", _g("ex:o a owl:Ontology ; owl:versionIRI ex:o1 ."))) == 1
    assert _run("GOV017", _g("ex:o a owl:Ontology .")) == []
    assert _run("GOV017", _g('ex:o a owl:Ontology ; owl:versionInfo "1" ; dcterms:dateAccepted "2024" .')) == []


def test_release_rules_are_independent() -> None:
    data = _g('ex:o a owl:Ontology ; owl:versionInfo "1" ; skos:changeNote "c" .')
    assert _run("GOV011", data) == []
    assert len(_run("GOV017", data)) == 1
    data = _g('ex:o a owl:Ontology ; owl:versionInfo "1" ; dcterms:dateAccepted "2024" .')
    assert len(_run("GOV011", data)) == 1
    assert _run("GOV017", data) == []


def test_gov013_messages_and_filters() -> None:
    data = _g("ex:Old a owl:DeprecatedClass . ex:A rdfs:subClassOf ex:Old .")
    assert [(f.focus, f.message) for f in _run("GOV013", data)] == [
        (BASE + "A", f"Obsolete term {BASE}Old appears as object of http://www.w3.org/2000/01/rdf-schema#subClassOf.")
    ]
    data = _g("ex:q a owl:DeprecatedProperty . ex:a ex:q ex:b .")
    assert [(f.focus, f.message) for f in _run("GOV013", data)] == [
        (BASE + "a", f"Obsolete property {BASE}q used in assertion.")
    ]
    # Referrers that are themselves retired are not flagged, in either position.
    assert (
        _run("GOV013", _g("ex:Old a owl:DeprecatedClass . ex:A owl:deprecated true ; rdfs:subClassOf ex:Old .")) == []
    )
    assert _run("GOV013", _g("ex:q a owl:DeprecatedProperty . ex:a owl:deprecated true ; ex:q ex:b .")) == []
    assert _run("GOV013", _g("ex:q a owl:DeprecatedProperty . ex:a a owl:DeprecatedClass ; ex:q ex:b .")) == []
    # Annotation-style references are fine.
    assert _run("GOV013", _g("ex:Old a owl:DeprecatedClass . ex:A rdfs:comment ex:Old .")) == []
    assert _run("GOV013", _g("ex:Old a owl:DeprecatedClass . ex:New dcterms:replaces ex:Old .")) == []
    assert _run("GOV013", _g("ex:Old a owl:DeprecatedClass . ex:A obo:IAO_0100001 ex:Old .")) == []


def test_gov013_literal_typed_and_owl_deprecated_marker_are_not_double_reported() -> None:
    data = _g("ex:Old a owl:DeprecatedClass ; owl:deprecated true . ex:A rdfs:subClassOf ex:Old .")
    assert _run("GOV013", data) == []
    data = _g("ex:Old a owl:DeprecatedProperty ; owl:deprecated true . ex:a ex:Old ex:b .")
    assert _run("GOV013", data) == []


def test_gov013_property_use_with_obsolete_subject_is_skipped() -> None:
    data = _g("ex:q a owl:DeprecatedProperty . ex:z a owl:DeprecatedClass . ex:z ex:q ex:b .")
    assert _run("GOV013", data) == []


def test_gov013_blank_node_restriction_focus() -> None:
    data = _g("ex:Old a owl:DeprecatedClass . [] owl:someValuesFrom ex:Old .")
    assert len(_run("GOV013", data)) == 1


def test_gov014_message_requires_base_and_axiom() -> None:
    data = _g("<https://other.test/T> a owl:Class ; rdfs:subClassOf ex:A .")
    found = _run("GOV014", data, base=BASE)
    assert [(f.focus, f.message) for f in found] == [
        ("https://other.test/T", f"Term is defined with axioms outside the base namespace {BASE}.")
    ]
    assert _run("GOV014", data) == []
    assert _run("GOV014", data, base="") == []
    assert _run("GOV014", _g("<https://other.test/T> a owl:Class ."), base=BASE) == []
    assert _run("GOV014", _g("<https://other.test/T> rdfs:subClassOf ex:A ."), base=BASE) == []


@pytest.mark.parametrize(
    "axiom",
    [
        "rdfs:subClassOf ex:A",
        "rdfs:subPropertyOf ex:A",
        "rdfs:domain ex:A",
        "rdfs:range ex:A",
        "owl:equivalentClass ex:A",
        "owl:equivalentProperty ex:A",
        "owl:disjointWith ex:A",
        "owl:inverseOf ex:A",
    ],
)
def test_gov014_each_defining_predicate(axiom: str) -> None:
    data = _g(f"<https://other.test/T> a owl:Class ; {axiom} .")
    assert len(_run("GOV014", data, base=BASE)) == 1


@pytest.mark.parametrize(
    "kind",
    [
        "owl:Class",
        "rdfs:Class",
        "owl:ObjectProperty",
        "owl:DatatypeProperty",
        "owl:AnnotationProperty",
        "rdf:Property",
        "skos:Concept",
        "skos:ConceptScheme",
        "skos:Collection",
        "owl:NamedIndividual",
    ],
)
def test_gov014_each_declared_kind(kind: str) -> None:
    data = _g(f"<https://other.test/T> a {kind} ; rdfs:subClassOf ex:A .")
    assert len(_run("GOV014", data, base=BASE)) == 1


@pytest.mark.parametrize("namespace", ["owl:", "rdf:", "rdfs:", "xsd:"])
def test_gov014_ignores_core_vocabulary_namespaces(namespace: str) -> None:
    data = _g(f"{namespace}Thing a owl:Class ; rdfs:subClassOf ex:A .")
    assert _run("GOV014", data, base=BASE) == []


def test_gov014_each_foreign_term_is_reported_sorted() -> None:
    data = _g(
        "<https://other.test/B> a owl:Class ; rdfs:subClassOf ex:A ."
        "<https://other.test/A> a owl:Class ; rdfs:subClassOf ex:A ."
    )
    assert [f.focus for f in _run("GOV014", data, base=BASE)] == ["https://other.test/A", "https://other.test/B"]


def test_gov014_base_without_trailing_separator_matches_namespace_boundary() -> None:
    data = _g("<https://example.test/ontology> a owl:Class ; rdfs:subClassOf ex:A .")
    assert len(_run("GOV014", data, base="https://example.test/onto")) == 1
    assert _run("GOV014", data, base="https://example.test/ontology") == []
