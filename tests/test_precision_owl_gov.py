"""Precision fixes for OWL001/005/006/011, GOV001/003, SKOS017, METRIC013 and ONT005 on real vocabularies."""

from __future__ import annotations

from typing import Any

import pytest
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.namespace import OWL, RDF, RDFS
from rule_harness import BASE, graph

from ontolint import Linter


def hits(turtle: str, rule: str, **options: Any) -> list[tuple[str, str]]:
    return [(f.focus, f.message) for f in Linter(graph(turtle), **options).execute([rule]).findings]


def foci(turtle: str, rule: str, **options: Any) -> list[str]:
    return sorted(focus for focus, _ in hits(turtle, rule, **options))


EX = BASE
PROP = "ex:p a owl:ObjectProperty ."


@pytest.mark.parametrize("namespace", ["http://schema.org/", "https://schema.org/", "http://purl.org/dc/dcam/"])
def test_owl005_owl006_accept_domain_and_range_includes(namespace: str) -> None:
    both = f"{PROP} ex:p <{namespace}domainIncludes> ex:A ; <{namespace}rangeIncludes> ex:A ."
    assert foci(both, "OWL005") == []
    assert foci(both, "OWL006") == []
    # each substitute only silences its own rule
    assert foci(f"{PROP} ex:p <{namespace}domainIncludes> ex:A .", "OWL006") == [EX + "p"]
    assert foci(f"{PROP} ex:p <{namespace}rangeIncludes> ex:A .", "OWL005") == [EX + "p"]


def test_owl005_owl006_still_report_bare_properties() -> None:
    assert foci(PROP, "OWL005") == [EX + "p"]
    assert foci(PROP, "OWL006") == [EX + "p"]
    assert foci(f"{PROP} ex:p rdfs:domain ex:A .", "OWL005") == []
    assert foci(f"{PROP} ex:p rdfs:range ex:A .", "OWL006") == []


def test_owl005_owl006_skip_deprecated_properties() -> None:
    deprecated = f"{PROP} ex:p owl:deprecated true ."
    assert foci(deprecated, "OWL005") == []
    assert foci(deprecated, "OWL006") == []
    assert foci(f"{PROP} ex:p owl:deprecated false .", "OWL005") == [EX + "p"]


def test_owl005_owl006_skip_pure_annotation_properties_only() -> None:
    assert foci("ex:a a owl:AnnotationProperty .", "OWL005") == []
    assert foci("ex:a a owl:AnnotationProperty .", "OWL006") == []
    assert foci("ex:a a owl:AnnotationProperty, owl:ObjectProperty .", "OWL005") == [EX + "a"]
    assert foci("ex:a a owl:AnnotationProperty, owl:DatatypeProperty .", "OWL006") == [EX + "a"]


def test_owl001_exempts_builtins_and_keeps_undeclared_local() -> None:
    turtle = "ex:A a owl:Class ; rdfs:subClassOf rdfs:Class, rdf:Property, owl:Thing, ex:Undeclared ."
    assert foci(turtle, "OWL001") == [EX + "Undeclared"]


_RESTRICTION = "ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom {} ] ."


def test_owl011_skips_datatype_fillers() -> None:
    assert foci(_RESTRICTION.format("xsd:gDay"), "OWL011") == []
    assert foci("ex:dt a rdfs:Datatype . " + _RESTRICTION.format("ex:dt"), "OWL011") == []
    expression = "[ a rdfs:Datatype ; owl:onDatatype xsd:integer ]"
    assert foci(_RESTRICTION.format(expression), "OWL011") == []
    assert foci(_RESTRICTION.format("[ owl:datatypeComplementOf xsd:integer ]"), "OWL011") == []
    assert foci("ex:p a owl:DatatypeProperty . " + _RESTRICTION.format("ex:X"), "OWL011") == []


def test_owl011_datatype_property_elsewhere_does_not_silence_unrelated_restriction() -> None:
    turtle = "ex:q a owl:DatatypeProperty . [ a owl:Restriction ; owl:allValuesFrom ex:X ] ."
    assert len(foci(turtle, "OWL011")) == 1


def test_owl011_reports_owning_class_and_keeps_object_restrictions() -> None:
    assert hits(_RESTRICTION.format("ex:B"), "OWL011") == [
        (EX + "A", f"Universal restriction on {EX}p does not imply any property value.")
    ]


def test_owl011_owner_found_through_intersection_and_two_restrictions_stay_distinct() -> None:
    turtle = (
        "ex:A owl:equivalentClass [ owl:intersectionOf ( ex:B [ owl:onProperty ex:p ; owl:allValuesFrom ex:B ] "
        "[ owl:onProperty ex:q ; owl:allValuesFrom ex:B ] ) ] ."
    )
    assert sorted(hits(turtle, "OWL011")) == [
        (EX + "A", f"Universal restriction on {EX}p does not imply any property value."),
        (EX + "A", f"Universal restriction on {EX}q does not imply any property value."),
    ]


def test_owl011_named_restriction_keeps_plain_message() -> None:
    turtle = "ex:R a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ."
    assert hits(turtle, "OWL011") == [(EX + "R", "Universal restriction does not imply any property value.")]


def test_owl011_some_values_from_alongside_is_exempt() -> None:
    assert hits("[ owl:onProperty ex:p ; owl:allValuesFrom ex:B ; owl:someValuesFrom ex:B ] .", "OWL011") == []


DEP = "ex:Old a owl:Class ; owl:deprecated true . ex:A a owl:Class ."


@pytest.mark.parametrize(
    "predicate",
    [
        "owl:annotatedSource",
        "owl:annotatedTarget",
        "owl:annotatedProperty",
        "<http://www.geneontology.org/formats/oboInOwl#consider>",
        "<http://www.geneontology.org/formats/oboInOwl#replaced_by>",
        "<http://purl.obolibrary.org/obo/IAO_0100001>",
        "dcterms:isReplacedBy",
        "dcterms:replaces",
        "rdfs:seeAlso",
    ],
)
def test_gov001_ignores_annotation_style_references(predicate: str) -> None:
    assert hits(f"{DEP} ex:A {predicate} ex:Old .", "GOV001") == []


def test_gov001_ignores_lists_owned_by_annotation_predicates() -> None:
    assert hits(f"{DEP} _:ax owl:annotatedTarget ( ex:A ex:Old ) .", "GOV001") == []


def test_gov001_reports_logical_uses_on_the_owner() -> None:
    sub = hits(f"{DEP} ex:A rdfs:subClassOf ex:Old .", "GOV001")
    assert sub == [(EX + "A", f"Deprecated term {EX}Old appears as object of {RDFS.subClassOf}.")]
    in_list = hits(f"{DEP} ex:A owl:equivalentClass [ owl:intersectionOf ( ex:A ex:Old ) ] .", "GOV001")
    assert in_list == [(EX + "A", f"Deprecated term {EX}Old appears in a list of {OWL.intersectionOf}.")]
    restriction = hits(f"{DEP} ex:A rdfs:subClassOf [ owl:onProperty ex:p ; owl:someValuesFrom ex:Old ] .", "GOV001")
    assert restriction == [(EX + "A", f"Deprecated term {EX}Old appears as object of {OWL.someValuesFrom}.")]


def test_gov001_deprecated_property_use_and_label_exemptions() -> None:
    turtle = "ex:old a owl:ObjectProperty ; owl:deprecated true . ex:i ex:old ex:j ."
    assert hits(turtle, "GOV001") == [(EX + "i", f"Deprecated property {EX}old used in assertion.")]
    assert hits(f"{DEP} ex:A rdfs:label ex:Old ; rdfs:comment ex:Old .", "GOV001") == []
    assert hits("ex:Old a owl:Class . ex:A rdfs:subClassOf ex:Old .", "GOV001") == []
    assert hits("ex:Old owl:deprecated false . ex:A rdfs:subClassOf ex:Old .", "GOV001") == []


def test_gov003_only_reports_owned_undeclared_terms() -> None:
    foreign = "ex:A a owl:Class ; owl:equivalentClass <http://xmlns.com/foaf/0.1/Person>, rdfs:Class ."
    assert hits(foreign, "GOV003", base=BASE) == []
    assert foci("ex:A a owl:Class ; owl:equivalentClass ex:Missing .", "GOV003", base=BASE) == [EX + "Missing"]


def test_gov003_without_base_ignores_foreign_namespaces() -> None:
    turtle = "ex:A a owl:Class ; owl:equivalentClass <http://xmlns.com/foaf/0.1/Person>, ex:Missing ."
    assert foci(turtle, "GOV003") == [EX + "Missing"]


def test_gov003_declared_property_in_equivalence_is_not_undeclared() -> None:
    assert foci("ex:A a owl:Class ; owl:equivalentClass ex:p . ex:p a rdf:Property .", "GOV003") == []


def test_skos017_flags_owned_targets_only() -> None:
    assert foci("ex:a a skos:Concept ; skos:exactMatch ex:missing .", "SKOS017") == [EX + "a"]
    foreign = (
        "ex:a a skos:Concept ; skos:exactMatch <http://elsewhere.example/x> ; "
        "skos:broader <http://elsewhere.example/y> ."
    )
    assert foci(foreign, "SKOS017") == []
    assert foci(foreign, "SKOS017", base=BASE) == []


def test_skos017_mapping_into_other_namespace_without_base_is_external() -> None:
    turtle = (
        "ex:a a skos:Concept ; skos:exactMatch <http://elsewhere.example/x> . "
        "ex:b a skos:Concept ; skos:broader ex:gone ."
    )
    assert hits(turtle, "SKOS017") == [(EX + "b", f"skos:broader target {EX}gone is not described in the graph.")]


def _blank_graph(named: int, free: int, structural: int = 0) -> Graph:
    g = Graph()
    for i in range(named):
        g.add((URIRef(f"{BASE}n{i}"), RDF.type, OWL.Class))
    for _ in range(free):
        g.add((BNode(), RDFS.label, Literal("free")))
    for _ in range(structural):
        g.add((BNode(), RDF.type, OWL.Restriction))
    return g


def test_metric013_counts_only_free_blank_nodes_and_boundary() -> None:
    def fired(g: Graph) -> bool:
        return bool(Linter(g).execute(["METRIC013"]).findings)

    assert not fired(_blank_graph(4, 6, 200))  # 6 of 10 is exactly the 0.60 limit; structure ignored
    assert fired(_blank_graph(3, 7, 200))  # 7 of 10
    assert not fired(_blank_graph(10, 0, 200))


@pytest.mark.parametrize(
    "turtle",
    [
        "[] a owl:Axiom .",
        "[] a owl:Restriction .",
        "[] a owl:Class .",
        "[] owl:intersectionOf ( ex:A ) .",
        "[] owl:annotatedSource ex:A .",
        "[] owl:onProperty ex:p .",
        "[] a owl:AllDisjointClasses .",
        "[] rdf:first ex:A ; rdf:rest rdf:nil .",
    ],
)
def test_metric013_structural_blank_nodes_do_not_count(turtle: str) -> None:
    named = "\n".join(f"ex:s{i} a owl:Class ." for i in range(10))
    many = "\n".join(turtle for _ in range(40))
    assert hits(named + "\n" + many, "METRIC013") == []


def test_metric013_free_blank_nodes_still_fire() -> None:
    assert len(hits("\n".join("[] a ex:Thing ." for _ in range(10)), "METRIC013")) == 1


@pytest.mark.parametrize(
    "creator",
    [
        "dcterms:creator",
        "dcterms:contributor",
        "<http://purl.org/dc/elements/1.1/contributor>",
        "<http://purl.org/pav/createdBy>",
    ],
)
def test_ont005_accepts_creator_like_predicates(creator: str) -> None:
    onto = "<https://example.test/onto> a owl:Ontology"
    assert hits(f'{onto} ; dcterms:created "2020-01-01" ; {creator} "A" .', "ONT005") == []
    assert len(hits(f'{onto} ; {creator} "A" .', "ONT005")) == 1
    assert len(hits(f'{onto} ; dcterms:created "2020-01-01" .', "ONT005")) == 1
