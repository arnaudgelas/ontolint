"""Pins exact behaviour of the SHACL quality rules (SHQ009, 010, 012, 014, 015, 016, 022, 023)."""

from __future__ import annotations

import pytest
from rdflib import Graph
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import Finding
from ontolint.rules import shacl_quality
from ontolint.rules.specs import FIXES, SEVERITY

NS = "https://example.test/onto#"
TWO = 2
FOUR = 4
CHAIN = 3000


def _run(rule: str, shapes: str | Graph | None) -> list[Finding]:
    """Run the module directly so the tests also work before the module is registered."""
    for spec in shacl_quality.SPECS:
        SEVERITY.setdefault(spec.rule_id, spec.severity.value)
        FIXES.setdefault(spec.rule_id, spec.suggestion)
    sg = graph(shapes) if isinstance(shapes, str) else shapes
    linter = Linter(graph("ex:A a owl:Class ."), sg, base=BASE)
    shacl_quality.run(linter.rule_context)
    return [f for f in linter.rule_context.findings if f.rule == rule]


def _messages(rule: str, shapes: str) -> list[str]:
    return sorted(f.message for f in _run(rule, shapes))


def _focus(rule: str, shapes: str) -> list[str]:
    return sorted(f.focus for f in _run(rule, shapes))


def test_specs_are_well_formed() -> None:
    assert [s.rule_id for s in shacl_quality.SPECS] == [
        "SHQ009", "SHQ010", "SHQ012", "SHQ014", "SHQ015", "SHQ016", "SHQ022", "SHQ023",
    ]  # fmt: skip
    assert {s.category for s in shacl_quality.SPECS} == {"heuristic"}
    assert {s.module for s in shacl_quality.SPECS} == {"shacl_quality"}
    assert {s.family for s in shacl_quality.SPECS} == {"SHQ"}
    assert {s.rule_id: s.severity.value for s in shacl_quality.SPECS} == {
        "SHQ009": "warning", "SHQ010": "warning", "SHQ012": "info", "SHQ014": "warning",
        "SHQ015": "warning", "SHQ016": "info", "SHQ022": "warning", "SHQ023": "warning",
    }  # fmt: skip


def test_no_shapes_graph_is_a_no_op() -> None:
    linter = Linter(graph("ex:A a owl:Class ."), None, base=BASE)
    shacl_quality.run(linter.rule_context)
    assert linter.rule_context.findings == []


# --- SHQ009 ----------------------------------------------------------------------------------


def test_shq009_messages_and_counts() -> None:
    assert _messages("SHQ009", "ex:S sh:in () .") == ["sh:in list is empty; no value can satisfy it."]
    assert _messages("SHQ009", "ex:S sh:in ( 1 1 ) .") == ["sh:in list repeats 1 member(s)."]
    assert _messages("SHQ009", "ex:S sh:in ( 'a' 'a' 'a' 'b' ) .") == ["sh:in list repeats 2 member(s)."]
    assert _focus("SHQ009", "ex:S sh:in () .") == [NS + "S"]


def test_shq009_negatives() -> None:
    assert _run("SHQ009", "ex:S sh:in ( 1 ) .") == []
    assert _run("SHQ009", "ex:S sh:in ( 1 '1' 1.0 ) .") == []  # distinct terms
    assert _run("SHQ009", "ex:S sh:in ( ex:a ex:b ) .") == []
    assert _run("SHQ009", "ex:S sh:in 'lit' .") == []
    assert _run("SHQ009", "ex:S sh:in _:l . _:l rdf:first 1 .") == []  # malformed list is not judged here


# --- SHQ010 ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "tag", ["en", "fr-CA", "zh-Hant-TW", "abcdefgh", "en-abcdefgh", "x-private", "en-1234", "i-klingon", "a"]
)
def test_shq010_accepts_well_formed_tags(tag: str) -> None:
    assert _run("SHQ010", f"ex:S sh:languageIn ( '{tag}' ) .") == []


@pytest.mark.parametrize(
    "tag", ["", "en_US", "abcdefghi", "en-abcdefghi", "en-", "-en", "1en", "en--US", "e n", "fr-é"]
)
def test_shq010_flags_malformed_tags(tag: str) -> None:
    assert _messages("SHQ010", f"ex:S sh:languageIn ( 'en' '{tag}' ) .") == [
        f"sh:languageIn member {tag} is not a well-formed language tag."
    ]


def test_shq010_non_literal_members_and_malformed_lists() -> None:
    assert _messages("SHQ010", "ex:S sh:languageIn ( ex:fr ) .") == [
        f"sh:languageIn member {NS}fr is not a well-formed language tag."
    ]
    assert len(_run("SHQ010", "ex:S sh:languageIn ( 'a_b' 'c_d' ) .")) == TWO
    assert _run("SHQ010", "ex:S sh:languageIn 'en_US' .") == []
    assert _run("SHQ010", "ex:S sh:languageIn _:l . _:l rdf:first 'a_b' .") == []


# --- SHQ012 ----------------------------------------------------------------------------------


def test_shq012_requires_true_uniquelang_and_a_foreign_datatype() -> None:
    message = f"sh:uniqueLang is vacuous with sh:datatype {XSD_STRING}; only rdf:langString values have a language."
    assert _messages("SHQ012", "ex:S sh:uniqueLang true ; sh:datatype xsd:string .") == [message]
    assert _run("SHQ012", "ex:S sh:uniqueLang true ; sh:datatype rdf:langString .") == []
    assert _run("SHQ012", "ex:S sh:uniqueLang false ; sh:datatype xsd:string .") == []
    assert _run("SHQ012", "ex:S sh:uniqueLang 'true' ; sh:datatype xsd:string .") == []
    assert _run("SHQ012", "ex:S sh:uniqueLang true .") == []
    assert _run("SHQ012", "ex:S sh:datatype xsd:string .") == []
    assert len(_run("SHQ012", "ex:S sh:uniqueLang true ; sh:datatype xsd:string, xsd:integer .")) == TWO
    assert _run("SHQ012", "ex:S sh:uniqueLang true ; sh:datatype 'x' .") == []


XSD_STRING = "http://www.w3.org/2001/XMLSchema#string"


# --- SHQ014 ----------------------------------------------------------------------------------


def test_shq014_values() -> None:
    sh = "http://www.w3.org/ns/shacl#"
    assert _messages("SHQ014", "ex:S sh:severity sh:Warn .") == [
        f"sh:severity value {sh}Warn is not sh:Info, sh:Warning or sh:Violation."
    ]
    assert _messages("SHQ014", "ex:S sh:severity 'sh:Info' .") == [
        "sh:severity value sh:Info is not sh:Info, sh:Warning or sh:Violation."
    ]
    assert len(_run("SHQ014", "ex:S sh:severity [] .")) == 1
    for ok in ("sh:Info", "sh:Warning", "sh:Violation", "ex:Fatal", "<urn:x>"):
        assert _run("SHQ014", f"ex:S sh:severity {ok} .") == [], ok
    assert len(_run("SHQ014", "ex:S sh:severity sh:Info, sh:Bad, sh:Worse .")) == TWO


# --- SHQ015 ----------------------------------------------------------------------------------


@pytest.mark.parametrize("flag", ["s", "m", "i", "x", "q", "smixq", "ixi", ""])
def test_shq015_accepts_xpath_flags(flag: str) -> None:
    assert _run("SHQ015", f"ex:S sh:pattern 'a' ; sh:flags '{flag}' .") == []


@pytest.mark.parametrize("flag", ["g", "u", "I", "ig", "s m", "iz"])
def test_shq015_flags_unknown_flag_characters(flag: str) -> None:
    assert _messages("SHQ015", f"ex:S sh:pattern 'a' ; sh:flags '{flag}' .") == [
        f"sh:flags value {flag} is not made of the flags s, m, i, x and q."
    ]


def test_shq015_without_pattern_and_non_literal() -> None:
    assert _messages("SHQ015", "ex:S sh:flags 'i' .") == ["sh:flags is used without an sh:pattern."]
    assert len(_run("SHQ015", "ex:S sh:flags 'g' .")) == TWO  # both problems are reported
    assert _messages("SHQ015", "ex:S sh:pattern 'a' ; sh:flags ex:i .") == [
        f"sh:flags value {NS}i is not made of the flags s, m, i, x and q."
    ]
    assert _run("SHQ015", "ex:S sh:pattern 'a' .") == []


# --- SHQ016 ----------------------------------------------------------------------------------


def test_shq016_cycle_sizes_and_focus() -> None:
    assert _messages("SHQ016", "ex:S sh:node ex:S .") == ["Shape is part of a reference cycle of 1 shape(s)."]
    shapes = "ex:A sh:node ex:B . ex:B sh:node ex:C . ex:C sh:node ex:A . ex:D sh:node ex:A ."
    assert _focus("SHQ016", shapes) == [NS + "A", NS + "B", NS + "C"]
    assert set(_messages("SHQ016", shapes)) == {"Shape is part of a reference cycle of 3 shape(s)."}


@pytest.mark.parametrize(
    "shapes",
    [
        "ex:A sh:not ex:A .",
        "ex:A sh:and ( ex:B ex:C ) . ex:C sh:or ( ex:A ex:D ) .",
        "ex:A sh:xone ( ex:A ex:B ) .",
        "ex:A sh:property ex:B . ex:B sh:qualifiedValueShape ex:A .",
        "ex:A sh:property ex:B . ex:B sh:node ex:A .",
        "ex:A sh:node ex:B . ex:B sh:node ex:A .",
    ],
)
def test_shq016_follows_every_reference_kind(shapes: str) -> None:
    assert _run("SHQ016", shapes)


def test_shq016_acyclic_graphs_and_unrelated_edges() -> None:
    assert _run("SHQ016", "ex:A sh:node ex:B . ex:B sh:node ex:C .") == []
    assert _run("SHQ016", "ex:A sh:node ex:B, ex:C . ex:B sh:node ex:D . ex:C sh:node ex:D .") == []
    assert _run("SHQ016", "ex:A sh:node ex:B . ex:B sh:targetClass ex:A .") == []  # targets are not references
    assert _run("SHQ016", "ex:A sh:node 'lit' .") == []
    assert _run("SHQ016", "ex:A sh:and 'lit' .") == []
    assert _run("SHQ016", "ex:A sh:and _:x . _:x rdf:first ex:A .") == []  # malformed list
    assert _focus("SHQ016", "ex:A sh:node ex:B . ex:B sh:node ex:A . ex:C sh:node ex:B . ex:D sh:node ex:E .") == [
        NS + "A",
        NS + "B",
    ]


def test_shq016_two_disjoint_cycles_and_deep_chain() -> None:
    shapes = "ex:A sh:node ex:B . ex:B sh:node ex:A . ex:C sh:node ex:D . ex:D sh:node ex:C ."
    assert len(_run("SHQ016", shapes)) == FOUR
    chain = "\n".join(f"ex:n{i} sh:node ex:n{i + 1} ." for i in range(CHAIN))
    assert _run("SHQ016", chain) == []
    closed = chain + f"\nex:n{CHAIN} sh:node ex:n0 ."
    assert len(_run("SHQ016", closed)) == CHAIN + 1


# --- SHQ022 ----------------------------------------------------------------------------------


def test_shq022_each_target_predicate() -> None:
    assert _messages("SHQ022", "ex:S sh:targetClass 'A' .") == ["sh:targetClass value A is not an IRI."]
    assert _messages("SHQ022", "ex:S sh:targetSubjectsOf 'p' .") == ["sh:targetSubjectsOf value p is not an IRI."]
    assert _messages("SHQ022", "ex:S sh:targetObjectsOf 4 .") == ["sh:targetObjectsOf value 4 is not an IRI."]
    assert len(_run("SHQ022", "ex:S sh:targetClass [] .")) == 1
    assert len(_run("SHQ022", "ex:S sh:targetClass 'a', 'b', ex:C .")) == TWO
    assert _run("SHQ022", "ex:S sh:targetClass ex:C ; sh:targetSubjectsOf ex:p ; sh:targetObjectsOf ex:q .") == []
    assert _run("SHQ022", "ex:S sh:targetNode 'lit', 1, [] .") == []


# --- SHQ023 ----------------------------------------------------------------------------------


def test_shq023_counts_distinct_paths() -> None:
    assert _messages("SHQ023", "ex:S sh:property ex:P . ex:P sh:minCount 1 .") == ["Property shape has no sh:path."]
    assert _focus("SHQ023", "ex:S sh:property ex:P . ex:P sh:minCount 1 .") == [NS + "P"]
    assert _messages("SHQ023", "ex:S sh:property ex:P . ex:P sh:path ex:a, ex:b .") == [
        "Property shape has 2 sh:path values."
    ]
    assert _messages("SHQ023", "ex:S sh:property ex:P . ex:P sh:path ex:a, ex:b, ex:c .") == [
        "Property shape has 3 sh:path values."
    ]
    assert _run("SHQ023", "ex:S sh:property ex:P . ex:P sh:path ex:a .") == []
    assert _run("SHQ023", "ex:S sh:property ex:P . ex:P sh:path ( ex:a ex:b ) .") == []  # sequence path is one value
    assert _run("SHQ023", "ex:S sh:property ex:P . ex:P sh:path [ sh:inversePath ex:a ] .") == []
    assert _run("SHQ023", "ex:S a sh:NodeShape ; sh:closed true .") == []
    assert _run("SHQ023", "ex:S sh:property 'lit' .") == []
    assert _run("SHQ023", "ex:S sh:property ex:P , ex:Q . ex:P sh:path ex:a . ex:Q sh:path ex:b .") == []


def test_shq023_typed_property_shape_and_blank_property_shape() -> None:
    assert _focus("SHQ023", "ex:P a sh:PropertyShape .") == [NS + "P"]
    assert len(_run("SHQ023", "ex:S sh:property [ sh:minCount 1 ] .")) == 1
    assert _run("SHQ023", "ex:P a sh:PropertyShape ; sh:path ex:a .") == []


def test_shared_property_shape_reports_once() -> None:
    shapes = "ex:S sh:property ex:P . ex:T sh:property ex:P ."
    assert len(_run("SHQ023", shapes)) == 1
