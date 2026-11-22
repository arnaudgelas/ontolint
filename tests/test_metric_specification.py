"""The METRIC specification amendments of #182 (see the ``metrics`` and ``measurements`` module docstrings).

Each case pins one sentence of the specification through ``Linter(...).execute([ID])``: the fixture either yields no
finding (``None``) or one whose message contains the given text, which carries the numerator and the denominator the
rule counted.  They were written from the probes behind the #182 review, so a change of the rule's behaviour, not
only of its text, fails a test.  The figures the documents quote for the 21-file calibration corpus are not pinned.
"""

# ruff: noqa: E501
from __future__ import annotations

from dataclasses import replace

import pytest
from rule_harness import graph

from ontolint import Linter
from ontolint.policy import Policy

HD = "<https://example.test/onto> a owl:Ontology .\n"


def _cls(n: int, extra: str = "", pre: str = "C") -> str:
    return "".join(f"ex:{pre}{i} a owl:Class {extra}.\n" for i in range(n))


def _foreign(n: int, via: str = "rdfs:subClassOf") -> str:
    return "".join(f"ex:C{i} a owl:Class ; {via} <https://foreign{i}.test/F{i}> .\n" for i in range(n))


def _props(n: int, kind: str = "owl:ObjectProperty") -> str:
    return "".join(f"ex:p{i} a {kind} .\n" for i in range(n))


def _imports(n: int) -> str:
    return " , ".join(f"<https://i{i}.test/>" for i in range(n))


def _blank(n: int, body: str = "ex:p ex:C0") -> str:
    return "".join(f"[ {body} ] .\n" for _ in range(n))


def _run(rule: str, ttl: str, **limits: float) -> list[str]:
    policy = replace(Policy(), **limits) if limits else None
    return [f.message for f in Linter(graph(ttl), policy=policy).execute([rule]).findings]


def _check(rule: str, ttl: str, expected: str | None, limits: dict[str, float]) -> None:
    messages = _run(rule, ttl, **limits)
    if expected is None:
        assert messages == []
    else:
        assert len(messages) == 1
        assert expected in messages[0]


# A1: the gate names its quantity and bites at 9 versus 10 of it.
GATE_CASES = [
    ("001 9 classes", "METRIC001", _cls(9), None, {}),
    ("001 10 classes", "METRIC001", _cls(10), "10 of 10 classes lack a label", {}),
    ("002 9 classes", "METRIC002", _cls(9), None, {}),
    ("002 10 classes", "METRIC002", _cls(10), "10 of 10 classes", {}),
    ("003 9 properties among 20 classes", "METRIC003", _props(9) + _cls(20), None, {}),
    (
        "003 10 annotation properties",
        "METRIC003",
        _props(10, "owl:AnnotationProperty"),
        "10 of 10 properties lack documentation",
        {},
    ),
    ("005 9 classes", "METRIC005", _cls(9), None, {}),
    ("005 10 classes", "METRIC005", _cls(10), "10 of 10 classes are orphans", {}),
    ("006 9 classes", "METRIC006", _cls(9), None, {}),
    ("006 10 classes", "METRIC006", _cls(10), "0 properties for 10 classes (0.00 < 0.10)", {}),
    ("007 9 classes", "METRIC007", _cls(9) + _props(46), None, {}),
    ("007 10 classes", "METRIC007", _cls(10) + _props(51), "51 properties for 10 classes (5.10 > 5.00)", {}),
    ("008 9 properties among 20 classes", "METRIC008", _props(9) + _cls(20), None, {}),
    (
        "008 10 properties",
        "METRIC008",
        _props(10),
        "10 of 10 object/datatype properties have neither domain nor range",
        {},
    ),
    (
        "009 9 labelled terms, 5 unlabelled",
        "METRIC009",
        "".join(f'ex:C{i} a owl:Class ; rdfs:label "x" .\n' for i in range(9)) + _cls(5, pre="D"),
        None,
        {},
    ),
    (
        "009 10 labelled terms",
        "METRIC009",
        "".join(f'ex:C{i} a owl:Class ; rdfs:label "x" .\n' for i in range(10)),
        "0 of 10 labelled terms",
        {},
    ),
    (
        "012 9 defined classes among 20",
        "METRIC012",
        "".join(f'ex:C{i} a owl:Class ; rdfs:comment "x" .\n' for i in range(9)) + _cls(11, pre="D"),
        None,
        {},
    ),
    (
        "012 10 defined classes",
        "METRIC012",
        "".join(f'ex:C{i} a owl:Class ; rdfs:comment "x" .\n' for i in range(10)),
        "10 defined classes average 1.00 words",
        {},
    ),
    # METRIC010 gates on references, not terms: 10 classes with 9 references stay silent
    ("010 9 references from 9 classes", "METRIC010", HD + _foreign(9), None, {}),
    ("010 9 references from 10 classes", "METRIC010", HD + _foreign(9) + "ex:C9 a owl:Class .\n", None, {}),
    ("010 10 references", "METRIC010", HD + _foreign(10), "10 of 10 structural references", {}),
    # METRIC013 gates on subjects, blank ones included
    ("013 9 blank subjects", "METRIC013", _blank(9), None, {}),
    ("013 10 blank subjects", "METRIC013", _blank(10), "10 of 10 subjects are blank nodes (1.00 > 0.60)", {}),
    (
        "013 9 blank and 5 named subjects",
        "METRIC013",
        _blank(9) + _cls(5),
        "9 of 14 subjects are blank nodes (0.64 > 0.60)",
        {},
    ),
    # METRIC011 has no gate at all; the override of the gate moves the others
    (
        "011 no gate, 11 imports",
        "METRIC011",
        f"<https://example.test/onto> owl:imports {_imports(11)} .\n",
        "11 distinct owl:imports (threshold 10)",
        {},
    ),
    ("override: 5 classes below the default gate", "METRIC001", _cls(5), None, {}),
    ("override: gate lowered to 5", "METRIC001", _cls(5), "5 of 5 classes lack a label", {"metric_min_sample": 5}),
]


@pytest.mark.parametrize(("name", "rule", "ttl", "expected", "limits"), GATE_CASES, ids=[c[0] for c in GATE_CASES])
def test_sample_gate_names_its_quantity(
    name: str, rule: str, ttl: str, expected: str | None, limits: dict[str, float]
) -> None:
    _check(rule, ttl, expected, limits)


# A2, A3: what METRIC010 reads, what it counts, and the ownership fallback.
OTHER = "https://other.test/"
METRIC010_CASES = [
    ("subClassOf to foreign IRIs", HD + _foreign(10), "10 of 10 structural references"),
    (
        "owl:equivalentClass is not read",
        HD + _cls(10) + "".join(f"ex:C{i} owl:equivalentClass <https://foreign{i}.test/F{i}> .\n" for i in range(10)),
        None,
    ),
    (
        "restriction fillers are not read",
        HD
        + _cls(10)
        + "".join(
            f"ex:C{i} rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom <https://foreign{i}.test/F{i}> ] .\n"
            for i in range(10)
        ),
        None,
    ),
    (
        "blank targets are not counted",
        HD
        + _cls(10)
        + "".join(
            f"ex:C{i} rdfs:subClassOf <https://foreign{i}.test/F{i}> , [ a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:C0 ] .\n"
            for i in range(10)
        ),
        "10 of 10 structural references",
    ),
    (
        "OWL targets are not counted",
        HD
        + _cls(10)
        + "".join(f"ex:C{i} rdfs:subClassOf owl:Thing , <https://foreign{i}.test/F{i}> .\n" for i in range(10)),
        "10 of 10 structural references",
    ),
    (
        "RDFS and XSD targets are not counted",
        HD
        + "".join(
            f"ex:C{i} a owl:Class ; rdfs:subClassOf rdfs:Resource , <https://foreign{i}.test/F{i}> .\nex:p{i} a owl:DatatypeProperty ; rdfs:range xsd:string .\n"
            for i in range(10)
        ),
        "10 of 10 structural references",
    ),
    (
        "domain and range of owned properties count",
        HD
        + "".join(
            f"ex:p{i} a owl:ObjectProperty ; rdfs:domain <https://foreign{i}.test/F{i}> ; rdfs:range <https://foreign{i}.test/G{i}> .\n"
            for i in range(5)
        ),
        "10 of 10 structural references",
    ),
    (
        "SKOS targets are foreign",
        HD
        + "".join(
            f"ex:C{i} a owl:Class ; rdfs:subClassOf <http://www.w3.org/2004/02/skos/core#Concept{i}> .\n"
            for i in range(10)
        ),
        "10 of 10 structural references",
    ),
    (
        "same-namespace targets are not foreign",
        HD
        + "".join(
            f"<https://example.test/onto#C{i}> a owl:Class ; rdfs:subClassOf <https://example.test/onto#P{i}> .\n"
            for i in range(10)
        ),
        None,
    ),
    (
        "another OBO ontology shares the namespace",
        "<http://purl.obolibrary.org/obo/x.owl> a owl:Ontology .\n"
        + "".join(
            f"<http://purl.obolibrary.org/obo/X_{i}> a owl:Class ; rdfs:subClassOf <http://purl.obolibrary.org/obo/Y_{i}> .\n"
            for i in range(10)
        ),
        None,
    ),
    (
        "an owned subject with a target of another namespace is foreign",
        HD
        + "".join(
            f"ex:C{i} a owl:Class ; rdfs:subClassOf <http://purl.obolibrary.org/obo/Y_{i}> .\n" for i in range(10)
        ),
        "10 of 10 structural references",
    ),
    (
        "fallback: header owns no term, namespaces split",
        "<https://a.test/onto> a owl:Ontology .\n"
        + "".join(
            f"<https://b.test/B{i}> a owl:Class ; rdfs:subClassOf <https://c.test/C{i}> .\n<https://c.test/C{i}> a owl:Class ; rdfs:subClassOf <https://b.test/B{i}> .\n"
            for i in range(5)
        ),
        "10 of 10 structural references",
    ),
    (
        "fallback: no header, namespaces split",
        "".join(
            f"<https://b.test/B{i}> a owl:Class ; rdfs:subClassOf <https://c.test/C{i}> .\n<https://c.test/C{i}> a owl:Class ; rdfs:subClassOf <https://b.test/B{i}> .\n"
            for i in range(5)
        ),
        "10 of 10 structural references",
    ),
]


@pytest.mark.parametrize(("name", "ttl", "expected"), METRIC010_CASES, ids=[c[0] for c in METRIC010_CASES])
def test_metric010_reads_only_some_predicates(name: str, ttl: str, expected: str | None) -> None:
    _check("METRIC010", ttl, expected, {})


# A4: METRIC011 counts distinct IRI objects of owl:imports whatever the subject, and prints integers.
METRIC011_CASES = [
    (
        "a subject other than the header counts",
        "<https://example.test/onto> a owl:Ontology ; owl:imports "
        + _imports(10)
        + " .\nex:Z owl:imports <https://zzz.test/> .\n",
        "11 distinct owl:imports (threshold 10)",
    ),
    (
        "literal and blank objects do not count",
        "<https://example.test/onto> owl:imports " + _imports(10) + ' , "lit" , [] .\n',
        None,
    ),
    (
        "the same import from two headers counts once",
        "<https://a.test/o1> a owl:Ontology ; owl:imports "
        + _imports(11)
        + " .\n<https://a.test/o2> a owl:Ontology ; owl:imports <https://i0.test/> .\n",
        "11 distinct owl:imports (threshold 10)",
    ),
    ("exactly the limit does not fire", f"<https://example.test/onto> owl:imports {_imports(10)} .\n", None),
]


@pytest.mark.parametrize(("name", "ttl", "expected"), METRIC011_CASES, ids=[c[0] for c in METRIC011_CASES])
def test_metric011_counts_distinct_import_objects(name: str, ttl: str, expected: str | None) -> None:
    _check("METRIC011", ttl, expected, {})


# A5: what connects a class for METRIC005.  Ten classes form a ring; X is the class under test; the limit is 0, so
# an orphan X yields "1 of 11" and a connected one yields nothing.
RING = (
    _cls(10, pre="Z")
    + "".join(f"ex:Z{i} rdfs:subClassOf ex:Z{(i + 1) % 10} .\n" for i in range(10))
    + "ex:X a owl:Class .\n"
)
ORPHAN = "1 of 11 classes are orphans"


def _restriction(kind: str, extra: str = "") -> str:
    return f"ex:Z0 rdfs:subClassOf [ a owl:Restriction ; owl:onProperty ex:p ; {kind} ex:X {extra}] ."


ORPHAN_CASES = [
    ("baseline: X alone is an orphan", "", ORPHAN),
    ("self-loop connects", "ex:X rdfs:subClassOf ex:X .", None),
    ("external subclass connects", "<https://other.test/S> rdfs:subClassOf ex:X .", None),
    ("external superclass connects", "ex:X rdfs:subClassOf <https://other.test/S> .", None),
    ("equivalentClass connects as subject", "ex:X owl:equivalentClass ex:Z0 .", None),
    ("equivalentClass connects as object", "ex:Z0 owl:equivalentClass ex:X .", None),
    ("someValuesFrom filler connects", _restriction("owl:someValuesFrom"), None),
    ("allValuesFrom filler connects", _restriction("owl:allValuesFrom"), None),
    ("onClass filler connects", _restriction("owl:onClass", "; owl:minQualifiedCardinality 1 "), None),
    ("rdfs:domain connects", "ex:p rdfs:domain ex:X .", None),
    ("rdfs:range connects", "ex:p rdfs:range ex:X .", None),
    ("schema.org domainIncludes object connects", "ex:p <http://schema.org/domainIncludes> ex:X .", None),
    ("dcam rangeIncludes object connects", "ex:p <http://purl.org/dc/dcam/rangeIncludes> ex:X .", None),
    ("typed instance connects", "ex:i a ex:X .", None),
    ("subclass of owl:Thing connects", "ex:X rdfs:subClassOf owl:Thing .", None),
    ("deprecated is not an orphan", "ex:X owl:deprecated true .", None),
    ("hasValue does not connect", _restriction("owl:hasValue"), ORPHAN),
    ("complementOf does not connect", "ex:U owl:complementOf ex:X .", ORPHAN),
    ("disjointUnionOf does not connect", "ex:Z0 owl:disjointUnionOf ( ex:X ex:Z1 ) .", ORPHAN),
    ("seeAlso does not connect", "ex:X rdfs:seeAlso ex:Z0 .", ORPHAN),
    ("disjointWith does not connect", "ex:X owl:disjointWith ex:Z0 .", ORPHAN),
    ("union member does not connect", "ex:U owl:unionOf ( ex:X ex:Z0 ) .", ORPHAN),
    ("intersection member does not connect", "ex:U owl:intersectionOf ( ex:X ex:Z0 ) .", ORPHAN),
    ("being the subject of domainIncludes does not connect", "ex:X <http://schema.org/domainIncludes> ex:Z0 .", ORPHAN),
]


@pytest.mark.parametrize(("name", "extra", "expected"), ORPHAN_CASES, ids=[c[0] for c in ORPHAN_CASES])
def test_metric005_what_connects_a_class(name: str, extra: str, expected: str | None) -> None:
    _check("METRIC005", RING + extra, expected, {"metric_max_orphan_ratio": 0.0})


# A6: METRIC004 gates on owned classes; a mean above 8 needs a parent with 9 owned subclasses, so 10 classes.
def _children(parent_count: int, kids: int) -> str:
    return _cls(parent_count) + "".join(f"ex:C{i} rdfs:subClassOf ex:C0 .\n" for i in range(1, kids + 1))


METRIC004_CASES = [
    ("9 classes, 8 subclasses: mean 8 is not above the limit", _children(9, 8), None, {}),
    (
        "10 classes, 9 subclasses: the mean 9 fires",
        _children(10, 9),
        "1 parent classes have 9.00 direct subclasses on average (threshold 8.00)",
        {},
    ),
    (
        "the gate counts owned classes: 5 classes, mean 4 above limit 1, silent",
        _children(5, 4),
        None,
        {"metric_max_mean_fanout": 1.0},
    ),
    (
        "the same with the gate lowered to 5 fires",
        _children(5, 4),
        "1 parent classes have 4.00 direct subclasses on average (threshold 1.00)",
        {"metric_max_mean_fanout": 1.0, "metric_min_sample": 5},
    ),
]


@pytest.mark.parametrize(("name", "ttl", "expected", "limits"), METRIC004_CASES, ids=[c[0] for c in METRIC004_CASES])
def test_metric004_gate_counts_owned_classes(
    name: str, ttl: str, expected: str | None, limits: dict[str, float]
) -> None:
    _check("METRIC004", ttl, expected, limits)


# A9: METRIC006 and METRIC007 say "properties" but count relation properties (annotation properties are left out).
def test_metric006_message_says_properties_and_counts_relations() -> None:
    ttl = _cls(20) + "ex:a1 a owl:AnnotationProperty . ex:a2 a owl:AnnotationProperty . ex:o a owl:ObjectProperty ."
    assert _run("METRIC006", ttl) == ["1 properties for 20 classes (0.05 < 0.10)."]


def test_metric007_message_says_properties_and_counts_relations() -> None:
    ttl = _cls(10) + _props(51) + "ex:a1 a owl:AnnotationProperty ."
    assert _run("METRIC007", ttl) == ["51 properties for 10 classes (5.10 > 5.00)."]


# A8: which blank subjects METRIC013 leaves out as structure (numerator and denominator are both blank nodes).
METRIC013_CASES = [
    ("blank typed owl:Ontology is counted", _blank(10, "a owl:Ontology"), "10 of 10 subjects are blank nodes"),
    (
        "blank typed owl:NamedIndividual is counted",
        _blank(10, "a owl:NamedIndividual"),
        "10 of 10 subjects are blank nodes",
    ),
    ("blank with only owl:members is counted", _blank(10, "owl:members ( ex:A )"), "10 of 10 subjects are blank nodes"),
    ("blank with an ordinary predicate is counted", _blank(10, "ex:p 1"), "10 of 10 subjects are blank nodes"),
    ("blank typed owl:Restriction is structural", _blank(10, "a owl:Restriction"), None),
]


@pytest.mark.parametrize(("name", "ttl", "expected"), METRIC013_CASES, ids=[c[0] for c in METRIC013_CASES])
def test_metric013_counts_non_structural_blank_subjects(name: str, ttl: str, expected: str | None) -> None:
    _check("METRIC013", ttl, expected, {})
