"""The DATA001 and DATA002 specifications (see the ``literals`` and ``consistency`` module docstrings).

Each case pins one sentence of the specification through ``Linter(...).execute([ID])``: the number of findings the
fixture yields, named after the situation it covers.  They were written from the probes behind the #182 review, so a
change of the rule's behaviour, not only of its text, fails a test.  A case that reports less or more than the
rule's title suggests documents a limit, not an endorsement.
"""

# ruff: noqa: E501
from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter

HD = "<https://example.test/onto> a owl:Ontology .\n"
BASE = "ex:A a owl:Class . ex:B a owl:Class . ex:A owl:disjointWith ex:B . "


def _d(rng: str, val: str, extra: str = "", ptype: str = "owl:DatatypeProperty") -> str:
    return f"ex:p a {ptype} ; rdfs:range {rng} . {extra} ex:s ex:p {val} ."


def _count(rule: str, ttl: str) -> int:
    return len(Linter(graph(ttl)).execute([rule]).findings)


DATATYPES = 2  # integer and boolean: the values 1 and 2 share a datatype, so they share a finding
DATA001_CASES = [
    ("string range, plain", _d("xsd:string", '"a"'), 0),
    ("string range, lang", _d("xsd:string", '"a"@en'), 0),
    ("int range 1", _d("xsd:positiveInteger", "1"), 0),
    ("int range 0 posint", _d("xsd:positiveInteger", "0"), 1),
    ("decimal range int literal", _d("xsd:decimal", "1"), 0),
    ("int range decimal lit", _d("xsd:integer", '"1.0"^^xsd:decimal'), 1),
    ("normalizedString in string", _d("xsd:string", '"a"^^xsd:normalizedString'), 1),
    ("date in dateTime", _d("xsd:dateTime", '"2020-01-01"^^xsd:date'), 1),
    ("plain in integer", _d("xsd:integer", '"a"'), 1),
    ("plain in date", _d("xsd:date", '"a"'), 1),
    ("ill-typed equal", _d("xsd:integer", '"abc"^^xsd:integer'), 0),
    ("ill-typed int lit in posint", _d("xsd:positiveInteger", '"abc"^^xsd:integer'), 1),
    ("non xsd range", _d("ex:R", '"a"'), 0),
    ("rdfs:Literal range", _d("rdfs:Literal", '"a"^^xsd:integer'), 0),
    ("blank range", "ex:p a owl:DatatypeProperty ; rdfs:range [ a rdfs:Datatype ] . ex:s ex:p 1 .", 0),
    ("two ranges", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:string, xsd:date . ex:s ex:p 1 .", 0),
    ("object prop", _d("xsd:string", "1", ptype="owl:ObjectProperty"), 0),
    ("undeclared", "ex:p rdfs:range xsd:string . ex:s ex:p 1 .", 0),
    ("foreign prop", "<http://f/p> a owl:DatatypeProperty ; rdfs:range xsd:string . ex:s <http://f/p> 1 .", 1),
    ("blank subject", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:string . [] ex:p 1 .", 1),
    ("two ranges same", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:string, xsd:string . ex:s ex:p 1 .", 1),
    ("int in string range", _d("xsd:string", "1"), 1),
    ("int in short range", _d("xsd:byte", "1000"), 1),
    ("int in short range ok", _d("xsd:byte", "100"), 0),
    ("int in nonPositive 0", _d("xsd:nonPositiveInteger", "0"), 0),
    ("int in unsignedLong -1", _d("xsd:unsignedLong", "-1"), 1),
    ("langString in string", _d("xsd:string", '"a"@en'), 0),
    ("double in decimal", _d("xsd:decimal", '"1.0"^^xsd:double'), 1),
    ("bool in int", _d("xsd:integer", "true"), 1),
    ("string lit explicit in int", _d("xsd:integer", '"1"^^xsd:string'), 1),
    ("lit in xsd:anyURI", _d("xsd:anyURI", '"http://x"'), 1),
    ("xsd:int range with int literal", _d("xsd:int", "1"), 0),
    ("non-xsd literal datatype", _d("xsd:string", '"a"^^ex:dt'), 1),
    ("lit in xsd:integer as decimal-valued in integer ill", _d("xsd:integer", '"1"^^xsd:positiveInteger'), 0),
]

DATA002_CASES = [
    ("object prop", BASE + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p ex:j .", 1),
    ("datatype prop", BASE + "ex:p a owl:DatatypeProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p 1 .", 1),
    ("annotation prop", BASE + "ex:p a owl:AnnotationProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p 1 .", 1),
    ("rdf:Property", BASE + "ex:p a rdf:Property ; rdfs:domain ex:A . ex:i a ex:B ; ex:p 1 .", 1),
    (
        "reverse disjoint",
        "ex:B owl:disjointWith ex:A . ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p ex:j .",
        1,
    ),
    ("undeclared p", BASE + "ex:p rdfs:domain ex:A . ex:i a ex:B ; ex:p ex:j .", 0),
    (
        "foreign p w/ header",
        HD + BASE + "<http://f/p> a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B ; <http://f/p> ex:j .",
        0,
    ),
    (
        "subclass of A",
        BASE + "ex:C rdfs:subClassOf ex:A . ex:p a owl:ObjectProperty ; rdfs:domain ex:C . ex:i a ex:B ; ex:p ex:j .",
        0,
    ),
    (
        "subclass of B",
        BASE + "ex:C rdfs:subClassOf ex:B . ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:C ; ex:p ex:j .",
        0,
    ),
    (
        "AllDisjointClasses",
        "ex:A a owl:Class . ex:B a owl:Class . [] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ) . ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p ex:j .",
        0,
    ),
    (
        "union domain",
        BASE + "ex:p a owl:ObjectProperty ; rdfs:domain [ owl:unionOf ( ex:A ex:C ) ] . ex:i a ex:B ; ex:p ex:j .",
        0,
    ),
    (
        "self-disjoint",
        "ex:A owl:disjointWith ex:A . ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:A ; ex:p ex:j .",
        1,
    ),
    ("two types", BASE + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B, ex:A ; ex:p ex:j .", 1),
    (
        "two domains",
        BASE
        + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A, ex:D . ex:D a owl:Class . ex:B owl:disjointWith ex:D . ex:i a ex:B ; ex:p ex:j .",
        2,
    ),
    ("blank subject", BASE + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . [ a ex:B ; ex:p ex:j ] .", 1),
    (
        "two uses one finding",
        BASE + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B ; ex:p ex:j, ex:k .",
        1,
    ),
    ("no use", BASE + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:i a ex:B .", 0),
    (
        "rdfs:domain on subproperty",
        BASE
        + "ex:q a owl:ObjectProperty ; rdfs:domain ex:A . ex:p a owl:ObjectProperty ; rdfs:subPropertyOf ex:q . ex:i a ex:B ; ex:p ex:j .",
        0,
    ),
    (
        "subject is object only",
        BASE + "ex:p a owl:ObjectProperty ; rdfs:domain ex:A . ex:j a ex:B . ex:i ex:p ex:j .",
        0,
    ),
    ("range", BASE + "ex:p a owl:ObjectProperty ; rdfs:range ex:A . ex:i ex:p ex:j . ex:j a ex:B .", 0),
]


@pytest.mark.parametrize(("situation", "ttl", "expected"), DATA001_CASES, ids=[c[0] for c in DATA001_CASES])
def test_data001_specification(situation: str, ttl: str, expected: int) -> None:
    assert _count("DATA001", ttl) == expected, situation


@pytest.mark.parametrize(("situation", "ttl", "expected"), DATA002_CASES, ids=[c[0] for c in DATA002_CASES])
def test_data002_specification(situation: str, ttl: str, expected: int) -> None:
    assert _count("DATA002", ttl) == expected, situation


def test_data001_examines_only_a_property_typed_owl_datatype_property() -> None:
    annotation = "ex:p a owl:AnnotationProperty ; rdfs:range xsd:string . ex:s ex:p 1 ."
    both = "ex:p a owl:AnnotationProperty, owl:DatatypeProperty ; rdfs:range xsd:string . ex:s ex:p 1 ."
    plain = "ex:p a rdf:Property ; rdfs:range xsd:string . ex:s ex:p 1 ."
    assert [_count("DATA001", t) for t in (annotation, both, plain)] == [0, 1, 0]


def test_data001_reports_one_finding_per_subject_property_and_offending_datatype() -> None:
    assert (
        _count("DATA001", "ex:p a owl:DatatypeProperty ; rdfs:range xsd:string . ex:s ex:p 1, 2, true .") == DATATYPES
    )


def test_data001_names_none_for_a_plain_literal() -> None:
    message = Linter(graph(_d("xsd:integer", '"a"'))).execute(["DATA001"]).findings[0].message
    assert message.endswith("but value has datatype None.")
