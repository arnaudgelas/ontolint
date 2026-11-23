"""Specification claims that no test pinned (issue #247): two limits at the limit and one past it, and the sentences of
``docs/measurements.md`` for METRIC002, METRIC009, METRIC010 and METRIC012.

Every case was probed against the code first; none found a defect, they pin what the text says.
"""

from __future__ import annotations

import pytest
from rule_harness import graph

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.policy import Policy
from ontolint.rules.measurements import CountRatio, measure, ratio

HEADER = "<https://example.test/onto> a owl:Ontology .\n"


def _count(rule: str, turtle: str) -> int:
    return sum(f.rule == rule for f in Linter(graph(turtle)).execute([rule]).findings)


# --- OWL019: an owl:AllDisjointProperties list of at most 200 members is read -------------------------------------


def _group(members: int) -> str:
    """A group whose last member is transitive, hence non-simple: it is reported only when the list is read."""
    properties = " ".join(f"ex:q{i}" for i in range(members - 1)) + " ex:t"
    declared = "".join(f"ex:q{i} a owl:ObjectProperty . " for i in range(members - 1))
    return (
        declared
        + "ex:t a owl:ObjectProperty, owl:TransitiveProperty . "
        + f"[ a owl:AllDisjointProperties ; owl:members ( {properties} ) ] ."
    )


@pytest.mark.parametrize(("members", "expected"), [(199, 1), (200, 1), (201, 0), (202, 0)])
def test_owl019_reads_an_all_disjoint_properties_list_of_at_most_200_members(members: int, expected: int) -> None:
    assert _count("OWL019", _group(members)) == expected


# --- OWL011: the owning term is the first IRI reached within eight hops --------------------------------------------


def _nested(depth: int, owner: str) -> str:
    """``owner`` has a chain of ``depth`` restrictions; the innermost, ``depth`` hops below it, is the only one with an
    ``owl:allValuesFrom`` and no ``owl:someValuesFrom``."""
    inner = "[ a owl:Restriction ; owl:onProperty ex:p ; owl:allValuesFrom ex:C ]"
    for _ in range(depth - 1):
        inner = f"[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom {inner} ]"
    return f"ex:Own a owl:Class . ex:p a owl:ObjectProperty . ex:C a owl:Class . {owner} rdfs:subClassOf {inner} ."


@pytest.mark.parametrize(("depth", "expected"), [(7, 0), (8, 0), (9, 1), (10, 1)])
def test_owl011_spares_a_restriction_held_by_a_foreign_term_only_within_eight_hops(depth: int, expected: int) -> None:
    assert _count("OWL011", _nested(depth, "<https://other.test/X>")) == expected


@pytest.mark.parametrize(("depth", "focus"), [(8, "ex:Own"), (9, None)])
def test_owl011_names_the_owner_within_eight_hops_and_the_restriction_beyond(depth: int, focus: str | None) -> None:
    (found,) = Linter(graph(_nested(depth, "ex:Own"))).execute(["OWL011"]).findings
    assert found.focus.endswith("onto#Own") if focus else found.focus.startswith("_:")


# --- docs/measurements.md ------------------------------------------------------------------------------------------


def _measured(turtle: str, measurement: str, **policy: object) -> tuple[int, int]:
    ctx = build_context(graph(HEADER + turtle), None, Policy(**policy))  # type: ignore[arg-type]
    assert measure(ctx, measurement) is not None
    return ratio(ctx, measurement)


@pytest.mark.parametrize(
    ("turtle", "expected"),
    [
        ('ex:A a owl:Class ; rdfs:comment "d" .', 1),
        ('ex:A a owl:Class ; skos:definition "d" .', 1),
        ('ex:A a owl:Class ; dcterms:description "d" .', 1),
        ('ex:A a owl:Class ; rdfs:comment "" .', 1),  # any value counts
        ("ex:A a owl:Class ; rdfs:comment ex:B .", 1),  # an IRI too
        ('ex:A a owl:Class ; skos:note "n" .', 0),  # not, unlike for LEX002
        ('ex:A a owl:Class ; skos:scopeNote "n" .', 0),
        ('ex:d rdfs:subPropertyOf skos:definition . ex:A a owl:Class ; ex:d "x" .', 1),
        ('ex:d owl:equivalentProperty rdfs:comment . ex:A a owl:Class ; ex:d "x" .', 1),
        ('ex:d rdfs:subPropertyOf ex:e . ex:e rdfs:subPropertyOf rdfs:comment . ex:A a owl:Class ; ex:d "x" .', 1),
    ],
)
def test_class_definition_coverage_counts_what_the_page_says(turtle: str, expected: int) -> None:
    assert _measured(turtle, "class_definition_coverage") == (expected, 1)


@pytest.mark.parametrize(
    ("turtle", "expected"),
    [
        ('ex:A a owl:Class ; rdfs:label "a"@en .', (1, 1)),
        ('ex:A a owl:Class ; rdfs:label "a" .', (0, 1)),
        ('ex:A a owl:Class ; rdfs:label "a"^^xsd:string .', (0, 1)),  # an xsd:string label is untagged
        ('ex:A a owl:Class ; rdfs:label "a", "b"@fr .', (1, 1)),  # one tagged label is enough
        ("ex:A a owl:Class .", (0, 0)),  # unlabelled terms are not in the population
        ('ex:A a owl:Class ; skos:altLabel "a"@en .', (0, 0)),
        ("ex:A a owl:Class ; rdfs:label ex:B .", (0, 0)),  # a label is a Literal
        ('ex:p a owl:ObjectProperty ; rdfs:label "p"@en .', (1, 1)),  # properties are in the population
        ('ex:A a owl:Class ; skos:prefLabel "a"@en .', (1, 1)),
    ],
)
def test_label_language_coverage_counts_what_the_page_says(turtle: str, expected: tuple[int, int]) -> None:
    assert _measured(turtle, "label_language_coverage") == expected


@pytest.mark.parametrize(
    ("turtle", "expected"),
    [
        ('ex:A a owl:Class ; rdfs:comment "one two three" .', (3, 1)),
        ('ex:A a owl:Class ; rdfs:comment "one two three" ; skos:definition "one two" .', (3, 1)),
        (
            'ex:A a owl:Class ; rdfs:comment "one" ; skos:definition "one two three four" .',
            (4, 1),
        ),  # the longest in words
        ('ex:A a owl:Class ; rdfs:comment "abcdefghijklmnopqrstuvwxyz" ; skos:definition "a b c" .', (3, 1)),
        ("ex:A a owl:Class ; rdfs:comment ex:B .", (0, 0)),  # an IRI description is not measured
        ('ex:A a owl:Class ; rdfs:comment "" .', (0, 1)),  # an empty literal is, and scores 0
        ('ex:p a owl:ObjectProperty ; rdfs:comment "one two" .', (0, 0)),  # properties are not measured
        ('ex:A a owl:Class ; rdfs:comment "a-b, c_d e.f" .', (5, 1)),  # \w+ tokens: a, b, c_d, e, f
    ],
)
def test_definition_length_counts_what_the_page_says(turtle: str, expected: tuple[int, int]) -> None:
    assert _measured(turtle, "definition_length") == expected


OTHER = "<https://other.test/ns#X>"


def _foreign(turtle: str) -> CountRatio:
    found = measure(build_context(graph(HEADER + turtle), None, Policy()), "foreign_references")
    assert isinstance(found, CountRatio)
    return found


@pytest.mark.parametrize(
    ("turtle", "expected"),
    [
        (f"ex:A a owl:Class ; rdfs:subClassOf {OTHER} .", (1, 1)),
        ("ex:A a owl:Class ; rdfs:subClassOf ex:B .", (0, 1)),  # the same namespace is a reference, not a foreign one
        (
            "ex:A a owl:Class ; rdfs:subClassOf owl:Thing .",
            (0, 0),
        ),  # outside the RDF, RDFS, OWL and XSD namespaces only
        ("ex:p a owl:DatatypeProperty ; rdfs:range xsd:string .", (0, 0)),
        (f"ex:p a owl:ObjectProperty ; rdfs:range {OTHER} .", (1, 1)),
        ("ex:A a owl:Class ; rdfs:subClassOf [ a owl:Restriction ] .", (0, 0)),  # blank targets are not counted
        (f"ex:A a owl:Class ; owl:equivalentClass {OTHER} .", (0, 0)),  # not read
        (
            "ex:A a owl:Class ; rdfs:subClassOf "
            f"[ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom {OTHER} ] .",
            (0, 0),
        ),  # fillers are not read
    ],
)
def test_foreign_references_counts_what_the_page_says(turtle: str, expected: tuple[int, int]) -> None:
    found = _foreign(turtle)
    assert (found.numerator, found.denominator) == expected


def test_foreign_references_by_namespace_is_sorted_and_masks_userinfo() -> None:
    turtle = (
        "ex:A a owl:Class ; rdfs:subClassOf <https://b.test/x#X>, <https://a.test/x#Y>, <https://a.test/x#Z>, "
        "<https://u:pw@c.test/ns#P>, <https://v:qq@c.test/ns#Q> ."
    )
    found = _foreign(turtle)
    names = found.by_namespace or ()
    assert [namespace for namespace, _ in names] == sorted(namespace for namespace, _ in names)
    assert dict(names) == {"https://a.test/x#": 2, "https://b.test/x#": 1, "https://****@c.test/ns#": 2}
    assert sum(count for _, count in names) == found.numerator


def test_a_target_in_the_subjects_obo_namespace_is_not_foreign() -> None:
    turtle = (
        "<http://purl.obolibrary.org/obo/X_1> a owl:Class ; rdfs:subClassOf <http://purl.obolibrary.org/obo/BFO_1> ."
    )
    ctx = build_context(graph("<http://purl.obolibrary.org/obo/onto> a owl:Ontology .\n" + turtle), None, Policy())
    found = measure(ctx, "foreign_references")
    assert isinstance(found, CountRatio)
    assert found.numerator == 0
