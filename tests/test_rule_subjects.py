"""The structured subject of findings that a rule can report several times on one focus.

A finding's identity is its rule, its focus and its subject (``Finding.subject``), never its message: these
cases pin, for each rule that reports more than one problem about the same focus, the subject that tells them
apart, in the rule's canonical order.
"""

from __future__ import annotations

import pytest
from rule_harness import BASE, graph

from ontolint import Linter

OWL = "http://www.w3.org/2002/07/owl#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
XSD = "http://www.w3.org/2001/XMLSchema#"


def _short(text: str) -> str:
    return text.removeprefix(BASE).replace(OWL, "owl:").replace(RDFS, "rdfs:").replace(XSD, "xsd:")


def subjects(rule: str, turtle: str, **options: object) -> set[tuple[str, tuple[str, ...]]]:
    """``(focus, subject)`` of every finding ``rule`` reports on ``turtle``, with the usual prefixes shortened."""
    findings = Linter(graph(turtle), **options).execute([rule]).findings  # type: ignore[arg-type]
    pairs = [(_short(f.focus), tuple(map(_short, f.subject))) for f in findings if f.rule == rule]
    assert len(pairs) == len(set(pairs)), f"{rule}: two findings share a subject: {pairs}"
    return set(pairs)


# --- OWL ---------------------------------------------------------------------------------------------


OWL_CASES = [
    (
        "OWL002",
        "ex:p rdfs:domain ex:A ; rdfs:range ex:B .",
        {("p", ("rdfs:domain",)), ("p", ("rdfs:range",))},
    ),
    (
        "OWL004",
        "ex:p a owl:ObjectProperty ; rdfs:domain ex:A, ex:B ; rdfs:range ex:C, ex:D .",
        {("p", ("rdfs:domain",)), ("p", ("rdfs:range",))},
    ),
    (
        "OWL009",
        "ex:p a owl:DatatypeProperty, owl:TransitiveProperty, owl:SymmetricProperty ; owl:inverseOf ex:q .",
        {("p", ("owl:inverseOf",)), ("p", ("owl:TransitiveProperty",)), ("p", ("owl:SymmetricProperty",))},
    ),
    (
        "OWL013",
        'ex:p a owl:ObjectProperty . ex:q a owl:ObjectProperty . ex:i ex:p "a" ; ex:q "b"@en .',
        {("i", ("p", '"a"')), ("i", ("q", '"b"@en'))},
    ),
    (
        "OWL018",
        "ex:p a owl:ReflexiveProperty, owl:IrreflexiveProperty, owl:AsymmetricProperty .",
        {
            ("p", ("owl:ReflexiveProperty", "owl:IrreflexiveProperty")),
            ("p", ("owl:ReflexiveProperty", "owl:AsymmetricProperty")),
        },
    ),
    (
        "OWL026",
        "ex:a owl:differentFrom ex:a . ex:a owl:sameAs ex:b ; owl:differentFrom ex:b .",
        {("a", ("a",)), ("a", ("b",))},
    ),
    (
        "OWL029",
        "ex:p a owl:AsymmetricProperty . ex:a ex:p ex:a, ex:b . ex:b ex:p ex:a .",
        {("a", ("p",)), ("a", ("p", "b"))},
    ),
    (
        "OWL031",
        "ex:A owl:unionOf () ; owl:intersectionOf ( ex:B ex:C ) ; owl:oneOf ex:x .",
        {("A", ("owl:unionOf", "empty")), ("A", ("owl:oneOf", "malformed"))},
    ),
    (
        "OWL045",
        "ex:x a owl:AllDifferent, owl:AllDisjointClasses .",
        {
            ("x", ("owl:AllDifferent", "no member list")),
            ("x", ("owl:AllDisjointClasses", "no member list")),
        },
    ),
    (
        "DATA001",
        "ex:p a owl:DatatypeProperty ; rdfs:range xsd:date . ex:q a owl:DatatypeProperty ; rdfs:range xsd:date ."
        ' ex:i ex:p "1"^^xsd:boolean ; ex:q "x" .',
        {("i", ("p", "xsd:boolean")), ("i", ("q", ""))},
    ),
]


@pytest.mark.parametrize(("rule", "turtle", "expected"), OWL_CASES, ids=[c[0] for c in OWL_CASES])
def test_owl_subjects(rule: str, turtle: str, expected: set[tuple[str, tuple[str, ...]]]) -> None:
    assert subjects(rule, turtle) == expected


def test_owl011_tells_a_general_class_axiom_from_a_restriction_of_the_class() -> None:
    turtle = """
        ex:p a owl:ObjectProperty .
        ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:B ] .
        [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:C ] rdfs:subClassOf ex:A .
    """
    assert subjects("OWL011", turtle) == {("A", ("p",)), ("A", ("general class axiom", "p"))}


def test_owl040_names_the_property_and_the_offending_value_not_its_repr() -> None:
    turtle = """
        ex:p a owl:ObjectProperty .
        ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;
            owl:hasValue "v" ; owl:allValuesFrom xsd:int ] .
    """
    found = subjects("OWL040", turtle)
    assert {s for _focus, s in found} == {("p", "owl:hasValue", '"v"'), ("p", "filler", "xsd:int")}


def test_owl036_and_owl037_keep_the_predicate_value_or_group_out_of_the_message() -> None:
    turtle = """
        ex:A rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ;
            owl:minCardinality "x" ; owl:maxCardinality 1 ; owl:cardinality 3 ] .
    """
    assert {s for _f, s in subjects("OWL036", turtle)} == {("owl:minCardinality", '"x"')}
    assert {s for _f, s in subjects("OWL037", turtle)} == {("unqualified",)}


def test_owl043_names_the_operator_the_use_and_the_operands() -> None:
    turtle = """
        ex:A owl:intersectionOf ( ex:B ex:C owl:Nothing ) . ex:B owl:disjointWith ex:C .
    """
    assert subjects("OWL043", turtle) == {
        ("A", ("owl:intersectionOf", "B", "C")),
        ("A", ("owl:intersectionOf", "owl:Nothing")),
    }
