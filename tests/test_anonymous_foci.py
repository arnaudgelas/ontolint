"""Findings on anonymous class expressions name a term and a property, never just a blank node."""

from __future__ import annotations

from rdflib import Graph

from ontolint import Linter

PREFIXES = (
    "@prefix owl: <http://www.w3.org/2002/07/owl#> . @prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .\n"
    "@prefix ex: <https://ex.test/o#> .\n<https://ex.test/o> a owl:Ontology .\n"
)


def _findings(rule: str, turtle: str) -> list[tuple[str, str]]:
    graph = Graph().parse(data=PREFIXES + turtle, format="turtle")
    return sorted((f.focus, f.message) for f in Linter(graph).execute([rule]).findings)


def test_owl043_on_an_anonymous_range_names_the_property() -> None:
    # The Software Description Ontology: rdfs:domain [ owl:unionOf ( ex:A owl:Thing ) ].
    turtle = "ex:p a owl:ObjectProperty ; rdfs:domain [ a owl:Class ; owl:unionOf ( ex:A owl:Thing ) ] ."
    assert _findings("OWL043", turtle) == [
        (
            "https://ex.test/o#p",
            "owl:unionOf in the rdfs:domain of https://ex.test/o#p contains owl:Thing; it is equivalent to owl:Thing.",
        )
    ]


def test_owl043_on_a_named_class_keeps_its_wording() -> None:
    assert _findings("OWL043", "ex:C owl:unionOf ( ex:A owl:Thing ) .") == [
        ("https://ex.test/o#C", "owl:unionOf contains owl:Thing; it is equivalent to owl:Thing.")
    ]


def test_owl011_in_a_general_class_axiom_names_the_class_and_property() -> None:
    # MOMo (food traceability): [ owl:allValuesFrom ... ] rdfs:subClassOf ex:Relation.
    turtle = (
        "ex:has a owl:ObjectProperty . ex:Relation a owl:Class .\n"
        "[ a owl:Restriction ; owl:onProperty ex:has ; owl:allValuesFrom ex:Thing ] rdfs:subClassOf ex:Relation ."
    )
    assert _findings("OWL011", turtle) == [
        (
            "https://ex.test/o#Relation",
            "Universal restriction on https://ex.test/o#has in a general class axiom about https://ex.test/o#Relation "
            "does not imply any value.",
        )
    ]


def test_owl011_on_a_class_keeps_its_wording() -> None:
    turtle = (
        "ex:has a owl:ObjectProperty .\n"
        "ex:C a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:has ; owl:allValuesFrom ex:D ] ."
    )
    assert _findings("OWL011", turtle) == [
        ("https://ex.test/o#C", "Universal restriction on https://ex.test/o#has does not imply any property value.")
    ]
