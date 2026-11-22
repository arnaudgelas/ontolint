"""``"x"`` and ``"x"^^xsd:string`` are one RDF literal, in OWL027, OWL033 and SHQ009 as in LEX003, LEX024 and SKOS020.

RDF 1.1 Concepts 3.3 makes a simple literal an ``xsd:string`` literal, so the two forms are one term; rdflib keeps
them apart.  The specifications of the three rules say they compare RDF terms, and the review of #182 found that
they did not: a negative assertion against ``"x"^^xsd:string`` of an asserted ``"x"`` raised nothing, a
``owl:oneOf`` holding both forms was not a repeat, and an ``sh:in`` list holding both was not repeated.  Other
datatypes stay apart (``"1"`` and ``"1"^^xsd:integer`` are two terms) and so do language tags.
"""

from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter

NPA = (
    "[ a owl:NegativePropertyAssertion ; owl:sourceIndividual ex:a ; owl:assertionProperty ex:s ; "
    "owl:targetValue {target} ] ."
)


def _count(rule: str, turtle: str, shapes: str | None = None) -> int:
    result = Linter(graph(turtle), graph(shapes) if shapes else None).execute([rule])
    return sum(finding.rule == rule for finding in result.findings)


@pytest.mark.parametrize(
    ("asserted", "target", "expected"),
    [
        ('"x"', '"x"^^xsd:string', 1),
        ('"x"^^xsd:string', '"x"', 1),
        ('"x"', '"x"', 1),
        ('"x"', '"x"@en', 0),
        ('"1"', '"1"^^xsd:integer', 0),
        ('"x"^^xsd:string', '"y"', 0),
    ],
)
def test_owl027_matches_literals_as_rdf_terms(asserted: str, target: str, expected: int) -> None:
    turtle = f"ex:a a owl:NamedIndividual . ex:s a owl:DatatypeProperty . ex:a ex:s {asserted} .\n" + NPA.format(
        target=target
    )
    assert _count("OWL027", turtle) == expected


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ('"x" "x"^^xsd:string', 1),
        ('"x"^^xsd:string "x"', 1),
        ('"x" "x"', 1),
        ('"x" "x"@en', 0),
        ('"x"@en "x"@EN', 1),
        ('"1" "1"^^xsd:integer', 0),
        ('"x" "y"^^xsd:string', 0),
    ],
)
def test_owl033_counts_a_plain_and_an_xsd_string_member_as_one_term(members: str, expected: int) -> None:
    assert (
        _count("OWL033", f"ex:C a owl:Class ; owl:equivalentClass [ a owl:Class ; owl:oneOf ( {members} ) ] .")
        == expected
    )


@pytest.mark.parametrize(
    ("members", "expected"),
    [
        ("'a' 'a'^^xsd:string", 1),
        ("'a'^^xsd:string 'a'", 1),
        ("'a' 'a'", 1),
        ("'a' 'a'@en", 0),
        ("'1' '1'^^xsd:integer", 0),
        ("'a' 'b'^^xsd:string", 0),
    ],
)
def test_shq009_counts_a_plain_and_an_xsd_string_member_as_one_term(members: str, expected: int) -> None:
    shapes = f"ex:S a sh:NodeShape ; sh:targetClass ex:A ; sh:in ( {members} ) ."
    assert _count("SHQ009", "ex:A a owl:Class .", shapes) == expected
