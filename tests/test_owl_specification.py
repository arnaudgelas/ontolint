"""The OWL specification amendments of #182 (see the ``owl``, ``owl_axioms`` and ``owl_expressions`` module docstrings).

Each case pins one sentence of the specification through ``Linter(graph(ttl)).execute([ID])``: the findings the
fixture yields (their focus and the part of the message that tells the situation apart), named after the situation it
covers.  They were written from the probes behind the #182 review, so a change of the rule's behaviour, not only of its
text, fails a test.
"""

# ruff: noqa: E501
from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter

HD = "<https://example.test/onto> a owl:Ontology .\n"
NS = "https://example.test/onto#"
BLANK = "_"


def _run(rule: str, ttl: str) -> list[tuple[str, str]]:
    findings = Linter(graph(ttl)).execute([rule]).findings
    return sorted(
        (BLANK if f.focus.startswith("_:") else f.focus.replace(NS, "ex:"), f.message.replace(NS, "ex:"))
        for f in findings
    )


def _chain(n: int, extra: str = "") -> str:
    return "ex:p " + extra + "owl:propertyChainAxiom ( " + " ".join(f"ex:q{i}" for i in range(n)) + " ) ."


def _inter(n: int) -> str:
    """An intersection of n members: a universal restriction, n-2 classes and its existential sibling."""
    return (
        "ex:p a owl:ObjectProperty . ex:C a owl:Class . ex:O owl:intersectionOf ( [ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:C ] "
        + " ".join(f"ex:k{i}" for i in range(n - 2))
        + " [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:C ] ) ."
    )


def _chain_functional(n: int) -> str:
    return (
        "ex:p a owl:ObjectProperty, owl:FunctionalProperty ; owl:propertyChainAxiom ( "
        + " ".join(f"ex:q{i}" for i in range(n))
        + " ) ."
    )


OWL011_ALL = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:C ]"
OWL011_SOME = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:C ]"
OWL011_HEAD = "ex:p a owl:ObjectProperty . ex:C a owl:Class . ex:Q a owl:Class . "
DEPRECATED = "ex:p a owl:ObjectProperty ; owl:deprecated "

# (situation, rule, ttl, expected findings as (focus, message))
CASES = [
    # A1: OWL024 / OWL025 focus is the member written first, in both written orders.
    (
        "OWL024 subject first (b)",
        "OWL024",
        "ex:b a owl:ObjectProperty . ex:a a owl:ObjectProperty . ex:b owl:propertyDisjointWith ex:a . ex:b rdfs:subPropertyOf ex:a .",
        [("ex:b", "disjoint with ex:a")],
    ),
    (
        "OWL024 subject first (a)",
        "OWL024",
        "ex:b a owl:ObjectProperty . ex:a a owl:ObjectProperty . ex:a owl:propertyDisjointWith ex:b . ex:b rdfs:subPropertyOf ex:a .",
        [("ex:a", "disjoint with ex:b")],
    ),
    (
        "OWL024 written in both orders: the least IRI first",
        "OWL024",
        "ex:b owl:propertyDisjointWith ex:a . ex:a owl:propertyDisjointWith ex:b . ex:b rdfs:subPropertyOf ex:a .",
        [("ex:a", "disjoint with ex:b")],
    ),
    (
        "OWL024 group, earlier member first (B A)",
        "OWL024",
        "[] a owl:AllDisjointProperties ; owl:members ( ex:B ex:A ) . ex:B rdfs:subPropertyOf ex:A .",
        [("ex:B", "disjoint with ex:A")],
    ),
    (
        "OWL024 group, earlier member first (A B)",
        "OWL024",
        "[] a owl:AllDisjointProperties ; owl:members ( ex:A ex:B ) . ex:B rdfs:subPropertyOf ex:A .",
        [("ex:A", "disjoint with ex:B")],
    ),
    (
        "OWL025 group, earlier member first (B A)",
        "OWL025",
        "ex:A a owl:Class . ex:B a owl:Class . [] a owl:AllDisjointClasses ; owl:members ( ex:B ex:A ) . ex:B rdfs:subClassOf ex:A .",
        [("ex:B", "disjoint with ex:A")],
    ),
    (
        "OWL025 group, earlier member first (A B)",
        "OWL025",
        "ex:A a owl:Class . ex:B a owl:Class . [] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ) . ex:B rdfs:subClassOf ex:A .",
        [("ex:A", "disjoint with ex:B")],
    ),
    (
        "OWL025 disjointWith subject first",
        "OWL025",
        "ex:B owl:disjointWith ex:A . ex:B rdfs:subClassOf ex:A .",
        [("ex:B", "disjoint with ex:A")],
    ),
    # A2: OWL044 reports n-1 findings for a same-as class of n members of one AllDifferent list.
    (
        "OWL044 three sameAs members give two findings",
        "OWL044",
        "ex:a owl:sameAs ex:b . ex:b owl:sameAs ex:c . [] a owl:AllDifferent ; owl:members ( ex:a ex:b ex:c ) .",
        [(BLANK, "contains ex:a and ex:b"), (BLANK, "contains ex:a and ex:c")],
    ),
    (
        "OWL044 owl:distinctMembers list",
        "OWL044",
        "ex:a owl:sameAs ex:b . [] a owl:AllDifferent ; owl:distinctMembers ( ex:a ex:b ) .",
        [(BLANK, "contains ex:a and ex:b")],
    ),
    # A3: one finding per subject, operator and kind (OWL031) or per axiom and kind (OWL045).
    (
        "OWL031 two malformed triples of one operator",
        "OWL031",
        'ex:h owl:unionOf "x", "y" .',
        [("ex:h", "owl:unionOf does not point")],
    ),
    (
        "OWL031 two operators, one finding each",
        "OWL031",
        'ex:h owl:unionOf "x" ; owl:intersectionOf "y" .',
        [("ex:h", "owl:intersectionOf does not point"), ("ex:h", "owl:unionOf does not point")],
    ),
    (
        "OWL031 malformed and empty are two kinds",
        "OWL031",
        'ex:h owl:unionOf "x", rdf:nil .',
        [("ex:h", "owl:unionOf does not point"), ("ex:h", "owl:unionOf list is empty")],
    ),
    (
        "OWL045 two malformed lists of one axiom, one finding of that kind",
        "OWL045",
        '[] a owl:AllDifferent ; owl:members "x", "y" .',
        [(BLANK, "more than one member list"), (BLANK, "member list is malformed")],
    ),
    (
        "OWL045 malformed lists on members and distinctMembers",
        "OWL045",
        '[] a owl:AllDifferent ; owl:members "x" ; owl:distinctMembers "y" .',
        [(BLANK, "more than one member list"), (BLANK, "member list is malformed")],
    ),
    (
        "OWL045 two axioms with a malformed list each",
        "OWL045",
        '[] a owl:AllDifferent ; owl:members "x" . [] a owl:AllDifferent ; owl:members "y" .',
        [(BLANK, "member list is malformed"), (BLANK, "member list is malformed")],
    ),
    # A5: OWL041 focuses the first node of the walk with a coloured neighbour of its own colour.
    (
        "OWL041 triangle is focused on c",
        "OWL041",
        "ex:a owl:complementOf ex:b . ex:b owl:complementOf ex:c . ex:c owl:complementOf ex:a .",
        [("ex:c", "odd cycle")],
    ),
    (
        "OWL041 five-cycle is focused on e3",
        "OWL041",
        "ex:e1 owl:complementOf ex:e2 . ex:e2 owl:complementOf ex:e3 . ex:e3 owl:complementOf ex:e4 . ex:e4 owl:complementOf ex:e5 . ex:e5 owl:complementOf ex:e1 .",
        [("ex:e3", "odd cycle")],
    ),
    ("OWL041 self-loop", "OWL041", "ex:s owl:complementOf ex:s .", [("ex:s", "odd cycle")]),
    ("OWL041 even cycle is consistent", "OWL041", "ex:a owl:complementOf ex:b . ex:b owl:complementOf ex:a .", []),
    # A6: OWL043 names where the expression is used only when its owning term uses it directly.
    (
        "OWL043 direct use names the clause",
        "OWL043",
        "ex:A owl:complementOf ex:B . ex:C11 rdfs:subClassOf [ owl:unionOf (ex:A ex:B) ] .",
        [("ex:C11", "owl:unionOf in the rdfs:subClassOf of ex:C11 contains complementary operands ex:A and ex:B")],
    ),
    (
        "OWL043 nested use has no clause",
        "OWL043",
        "ex:A owl:complementOf ex:B . ex:C11 rdfs:subClassOf [ owl:intersectionOf ( [ owl:unionOf (ex:A ex:B) ] ex:K ) ] .",
        [("ex:C11", "owl:unionOf contains complementary operands ex:A and ex:B")],
    ),
    # A7: OWL001 ownership fallback, a foreign IRI is owned when the ontology owns no declared term.
    (
        "OWL001 no owned declared term: foreign IRI reported",
        "OWL001",
        "<http://other/x> rdfs:subClassOf ex:A .",
        [("ex:A", "not explicitly declared a class"), ("http://other/x", "not explicitly declared a class")],
    ),
    (
        "OWL001 header and an owned declared term: foreign IRI spared",
        "OWL001",
        HD + "<http://other/x> rdfs:subClassOf ex:A . ex:A a owl:Class .",
        [],
    ),
    # A8: OWL005 / OWL006 owl:deprecated literal whose trimmed lowercased text is true or 1, whatever the datatype.
    ("OWL005 deprecated true", "OWL005", DEPRECATED + "true .", []),
    ("OWL005 deprecated TRUE string", "OWL005", DEPRECATED + '"TRUE" .', []),
    ("OWL005 deprecated padded", "OWL005", DEPRECATED + '" true " .', []),
    ("OWL005 deprecated 1 boolean", "OWL005", DEPRECATED + '"1"^^xsd:boolean .', []),
    ("OWL005 deprecated 1 string", "OWL005", DEPRECATED + '"1" .', []),
    ("OWL005 deprecated yes", "OWL005", DEPRECATED + '"yes" .', [("ex:p", "no asserted rdfs:domain")]),
    ("OWL005 deprecated false", "OWL005", DEPRECATED + "false .", [("ex:p", "no asserted rdfs:domain")]),
    ("OWL006 deprecated TRUE string", "OWL006", DEPRECATED + '"TRUE" .', []),
    ("OWL006 deprecated 1 boolean", "OWL006", DEPRECATED + '"1"^^xsd:boolean .', []),
    ("OWL006 deprecated 0", "OWL006", DEPRECATED + '"0" .', [("ex:p", "no asserted rdfs:range")]),
    ("OWL006 deprecated IRI", "OWL006", DEPRECATED + "ex:x .", [("ex:p", "no asserted rdfs:range")]),
    # A9: the 500-member list limit of OWL010, OWL011 and OWL019, at 500 and at 501.
    ("OWL010 chain of 500 is a list", "OWL010", _chain(500), []),
    ("OWL010 chain of 501 is malformed", "OWL010", _chain(501), [("ex:p", "does not point to a well-formed RDF list")]),
    (
        "OWL019 functional chain of 500 members",
        "OWL019",
        _chain_functional(500),
        [("ex:p", "defined by a property chain")],
    ),
    ("OWL019 functional chain of 501 members is no chain", "OWL019", _chain_functional(501), []),
    ("OWL011 intersection of 500 members has the sibling", "OWL011", _inter(500), []),
    (
        "OWL011 intersection of 501 members is malformed, no sibling",
        "OWL011",
        _inter(501),
        [("ex:O", "Universal restriction on ex:p")],
    ),
    # A10: OWL011 sibling restrictions held by the members of an intersection.
    (
        "OWL011 sibling in an intersection defining a superclass",
        "OWL011",
        OWL011_HEAD
        + f"ex:O a owl:Class ; rdfs:subClassOf {OWL011_ALL}, ex:Q . ex:Q owl:intersectionOf ( {OWL011_SOME} ex:C ) .",
        [],
    ),
    (
        "OWL011 no sibling",
        "OWL011",
        OWL011_HEAD + f"ex:O a owl:Class ; rdfs:subClassOf {OWL011_ALL}, ex:Q .",
        [("ex:O", "Universal restriction on ex:p")],
    ),
    (
        "OWL011 sibling in an intersection that is itself a sibling",
        "OWL011",
        f"ex:p a owl:ObjectProperty . ex:C a owl:Class . ex:O a owl:Class ; rdfs:subClassOf {OWL011_ALL}, [ owl:intersectionOf ( {OWL011_SOME} ex:C ) ] .",
        [],
    ),
    (
        "OWL011 inherited existential is not followed",
        "OWL011",
        OWL011_HEAD + f"ex:O a owl:Class ; rdfs:subClassOf {OWL011_ALL}, ex:Q . ex:Q rdfs:subClassOf {OWL011_SOME} .",
        [("ex:O", "Universal restriction on ex:p")],
    ),
    # A11: OWL022 reads a range typed owl:Class or both kinds as no datatype / no class.
    (
        "OWL022 object property, xsd IRI typed owl:Class",
        "OWL022",
        "ex:od a owl:ObjectProperty ; rdfs:range xsd:fake . xsd:fake a owl:Class .",
        [],
    ),
    (
        "OWL022 object property, xsd IRI untyped",
        "OWL022",
        "ex:od a owl:ObjectProperty ; rdfs:range xsd:fake .",
        [("ex:od", "datatype range http://www.w3.org/2001/XMLSchema#fake")],
    ),
    (
        "OWL022 object property, range both Class and Datatype",
        "OWL022",
        "ex:od a owl:ObjectProperty ; rdfs:range ex:D . ex:D a owl:Class, rdfs:Datatype .",
        [],
    ),
    (
        "OWL022 object property, range Datatype only",
        "OWL022",
        "ex:od a owl:ObjectProperty ; rdfs:range ex:D . ex:D a rdfs:Datatype .",
        [("ex:od", "datatype range ex:D")],
    ),
    (
        "OWL022 object property, rdfs:Literal range",
        "OWL022",
        "ex:op a owl:ObjectProperty ; rdfs:range rdfs:Literal .",
        [("ex:op", "datatype range http://www.w3.org/2000/01/rdf-schema#Literal")],
    ),
    (
        "OWL022 object property, rdfs:Literal typed owl:Class",
        "OWL022",
        "ex:op a owl:ObjectProperty ; rdfs:range rdfs:Literal . rdfs:Literal a owl:Class .",
        [],
    ),
    (
        "OWL022 datatype property, class range",
        "OWL022",
        "ex:dp a owl:DatatypeProperty ; rdfs:range ex:C . ex:C a owl:Class .",
        [("ex:dp", "class range ex:C")],
    ),
    (
        "OWL022 datatype property, range both Class and Datatype",
        "OWL022",
        "ex:dp a owl:DatatypeProperty ; rdfs:range ex:C . ex:C a owl:Class, rdfs:Datatype .",
        [],
    ),
    (
        "OWL022 datatype property, owl:Thing range",
        "OWL022",
        "ex:dp a owl:DatatypeProperty ; rdfs:range owl:Thing .",
        [("ex:dp", "class range http://www.w3.org/2002/07/owl#Thing")],
    ),
    (
        "OWL022 datatype property, blank range",
        "OWL022",
        "ex:dp a owl:DatatypeProperty ; rdfs:range [ a owl:Class ] .",
        [],
    ),
    # A12: OWL008 checks no ownership.
    (
        "OWL008 foreign symmetric property",
        "OWL008",
        HD + "<http://f/p> a owl:SymmetricProperty ; owl:inverseOf <http://f/q> . ex:z a owl:Class .",
        [("http://f/p", "also declared inverse of http://f/q")],
    ),
    # A13: OWL040 reads a filler typed both owl:Class and rdfs:Datatype as a datatype.
    (
        "OWL040 object property, filler typed Class and Datatype",
        "OWL040",
        "ex:op a owl:ObjectProperty . ex:D a owl:Class, rdfs:Datatype . [ a owl:Restriction ; owl:onProperty ex:op ; owl:someValuesFrom ex:D ] .",
        [(BLANK, "uses datatype filler ex:D")],
    ),
    (
        "OWL040 datatype property, filler typed Class and Datatype",
        "OWL040",
        "ex:dp a owl:DatatypeProperty . ex:D a owl:Class, rdfs:Datatype . [ a owl:Restriction ; owl:onProperty ex:dp ; owl:someValuesFrom ex:D ] .",
        [],
    ),
    (
        "OWL040 object property, class filler",
        "OWL040",
        "ex:op a owl:ObjectProperty . ex:D a owl:Class . [ a owl:Restriction ; owl:onProperty ex:op ; owl:someValuesFrom ex:D ] .",
        [],
    ),
]


@pytest.mark.parametrize(("situation", "rule", "ttl", "expected"), CASES, ids=[c[0] for c in CASES])
def test_owl_specification(situation: str, rule: str, ttl: str, expected: list[tuple[str, str]]) -> None:
    found = _run(rule, ttl)
    assert len(found) == len(expected), (situation, found)
    for (focus, message), (want_focus, fragment) in zip(found, expected, strict=True):
        assert focus == want_focus, (situation, found)
        assert fragment in message, (situation, found)
