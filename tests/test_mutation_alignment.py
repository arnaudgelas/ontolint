"""Targeted tests that pin behaviour of the alignment rules (exact messages, boundaries, operands)."""

from __future__ import annotations

from typing import Any

from rdflib import Graph
from rule_harness import graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding

EXT = "@prefix a: <http://a.test/> . @prefix b: <http://b.test/> . @prefix c: <http://c.test/> .\n"
A, B, C = "http://a.test/", "http://b.test/", "http://c.test/"
TWO = 2
OTHER = {"base": "http://elsewhere.test/"}


def _run(rule: str, turtle: str, **options: Any) -> list[Finding]:
    data: Graph = graph(EXT + turtle)
    result = Linter(data, None, **options).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _messages(rule: str, turtle: str, **options: Any) -> list[str]:
    return [f.message for f in _run(rule, turtle, **options)]


# --- ALIGN002 --------------------------------------------------------------------------------


def test_align002_message_hints_the_intended_property() -> None:
    found = _run("ALIGN002", "ex:A skos:exactmatch a:A .")
    assert [(f.focus, f.message, f.confidence) for f in found] == [
        (
            "https://example.test/onto#A",
            "http://www.w3.org/2004/02/skos/core#exactmatch is not a SKOS or OWL mapping property; "
            "did you mean skos:exactMatch?",
            "certain",
        )
    ]
    assert _messages("ALIGN002", "ex:A owl:sameas a:A .") == [
        "http://www.w3.org/2002/07/owl#sameas is not a SKOS or OWL mapping property; did you mean owl:sameAs?"
    ]


def test_align002_unknown_match_has_no_hint_and_non_match_predicates_are_ignored() -> None:
    assert _messages("ALIGN002", "ex:A skos:relMatch a:A .") == [
        "http://www.w3.org/2004/02/skos/core#relMatch is not a SKOS or OWL mapping property"
    ]
    assert _messages("ALIGN002", "ex:A skos:prefLabel 'x' ; owl:versionInfo 'v' ; owl:foo 'x' .") == []
    # "match" in the name only matters inside the SKOS namespace.
    assert _messages("ALIGN002", "ex:A owl:matchmaker a:A .") == []


def test_align002_only_scoped_and_iri_subjects() -> None:
    assert _messages("ALIGN002", "ex:A skos:exactmatch a:A .", **OTHER) == []
    assert _messages("ALIGN002", "[] skos:exactmatch a:A .") == []


# --- ALIGN003 --------------------------------------------------------------------------------


def test_align003_message_and_focus() -> None:
    found = _run("ALIGN003", "a:X skos:exactMatch b:Y . b:Y skos:exactMatch c:Z . a:X skos:broadMatch c:Z .")
    assert [(f.focus, f.message) for f in found] == [
        (
            A + "X",
            f"{A}X and {C}Z are exactMatch-equivalent through a chain but also linked by broadMatch/narrowMatch.",
        )
    ]


def test_align003_narrowMatch_orientation_names_the_narrow_term_first() -> None:
    found = _run("ALIGN003", "a:X skos:exactMatch b:Y . b:Y skos:exactMatch c:Z . a:X skos:narrowMatch c:Z .")
    assert [f.focus for f in found] == [C + "Z"]


def test_align003_scope_uses_either_endpoint_and_a_direct_pair_is_left_to_skos012() -> None:
    turtle = "ex:X skos:exactMatch b:Y . b:Y skos:exactMatch c:Z . ex:X skos:broadMatch c:Z ."
    assert len(_messages("ALIGN003", turtle)) == 1
    assert _messages("ALIGN003", turtle, **OTHER) == []
    only_target = "a:X skos:exactMatch b:Y . b:Y skos:exactMatch ex:Z . a:X skos:broadMatch ex:Z ."
    assert len(_messages("ALIGN003", only_target, base="https://example.test/")) == 1
    assert _messages("ALIGN003", "a:X skos:exactMatch b:Y . a:X skos:narrowMatch b:Y .") == []
    assert _messages("ALIGN003", "a:X skos:exactMatch b:Y . b:Y skos:exactMatch a:X . a:X skos:broadMatch b:Y .") == []


# --- ALIGN004 --------------------------------------------------------------------------------


def test_align004_reports_a_mutual_pair_once_with_the_smaller_iri_as_focus() -> None:
    found = _run("ALIGN004", "b:Y skos:broadMatch a:X . a:X skos:broadMatch b:Y .")
    assert [(f.focus, f.message) for f in found] == [
        (A + "X", f"{A}X and {B}Y are each mapped as broader than the other.")
    ]
    mixed = _run("ALIGN004", "a:X skos:broadMatch b:Y ; skos:narrowMatch b:Y .")
    assert [f.focus for f in mixed] == [A + "X"]


def test_align004_related_with_hierarchy_message_and_scope() -> None:
    found = _run("ALIGN004", "a:X skos:relatedMatch b:Y ; skos:broadMatch b:Y .")
    assert [(f.focus, f.message) for f in found] == [
        (A + "X", f"{A}X and {B}Y are linked by skos:relatedMatch and by broadMatch/narrowMatch.")
    ]
    assert _messages("ALIGN004", "a:X skos:relatedMatch b:Y ; skos:broadMatch b:Y .", **OTHER) == []
    assert _messages("ALIGN004", "a:X skos:broadMatch b:Y . b:Y skos:broadMatch a:X .", **OTHER) == []
    assert (
        len(_messages("ALIGN004", "ex:X skos:relatedMatch b:Y ; skos:broadMatch b:Y .", base="https://example.test/"))
        == 1
    )
    assert (
        len(_messages("ALIGN004", "a:X skos:relatedMatch ex:Y ; skos:broadMatch ex:Y .", base="https://example.test/"))
        == 1
    )
    assert (
        len(
            _messages("ALIGN004", "ex:X skos:broadMatch b:Y . b:Y skos:broadMatch ex:X .", base="https://example.test/")
        )
        == 1
    )
    assert (
        len(
            _messages("ALIGN004", "a:X skos:broadMatch ex:Y . ex:Y skos:broadMatch a:X .", base="https://example.test/")
        )
        == 1
    )


# --- ALIGN005 --------------------------------------------------------------------------------


def test_align005_message_lists_sorted_targets() -> None:
    found = _run("ALIGN005", "ex:S skos:exactMatch a:Two, a:One .")
    assert [(f.focus, f.message, f.confidence) for f in found] == [
        (
            "https://example.test/onto#S",
            f"Term has 2 distinct skos:exactMatch targets in {A}: {A}One, {A}Two.",
            "heuristic",
        )
    ]


def test_align005_equivalence_bridges_do_not_count_but_the_source_itself_does_not_bridge() -> None:
    bridge = (
        "ex:S skos:exactMatch a:One, a:Two . a:One owl:equivalentClass a:Mid . a:Mid owl:equivalentProperty a:Two ."
    )
    assert _messages("ALIGN005", bridge) == []
    inbound = "ex:S skos:exactMatch a:One, a:Two . a:Two owl:sameAs a:One ."
    assert _messages("ALIGN005", inbound) == []
    # Another source with the same two targets is reported too; it does not bridge them.
    other_source = "ex:S skos:exactMatch a:One, a:Two . ex:T skos:exactMatch a:One, a:Two ."
    assert len(_messages("ALIGN005", other_source)) == TWO
    chain = "ex:S skos:exactMatch a:One, a:Two, a:Three . a:One owl:sameAs a:Two ."
    assert [f.message for f in _run("ALIGN005", chain)] == [
        f"Term has 3 distinct skos:exactMatch targets in {A}: {A}One, {A}Three, {A}Two."
    ]


def test_align005_each_namespace_is_counted_separately_and_local_scope_applies() -> None:
    both = "ex:S skos:exactMatch a:One, a:Two, b:One, b:Two, c:One ."
    found = _run("ALIGN005", both)
    assert [f.message[:44] for f in found] == [
        f"Term has 2 distinct skos:exactMatch targets in {A}"[:44],
        f"Term has 2 distinct skos:exactMatch targets in {B}"[:44],
    ]
    assert _messages("ALIGN005", "ex:S skos:exactMatch a:One, a:Two .", **OTHER) == []
    assert _messages("ALIGN005", "ex:S skos:exactMatch <urn:x>, <urn:y> .") == []
    assert _messages("ALIGN005", 'ex:S skos:exactMatch a:One, "lit" , [] .') == []


# --- ALIGN007 --------------------------------------------------------------------------------


def test_align007_message_and_both_operands_of_every_condition() -> None:
    found = _run("ALIGN007", "ex:A skos:closeMatch ex:B . ex:B skos:prefLabel 'B' .")
    assert [(f.focus, f.message) for f in found] == [
        (
            "https://example.test/onto#A",
            "skos:closeMatch to https://example.test/onto#B has no inverse assertion, although "
            "https://example.test/onto#B is described here.",
        )
    ]
    base = {"base": "https://example.test/"}
    assert _messages("ALIGN007", "a:A skos:exactMatch ex:B . ex:B a skos:Concept .", **base) == []
    assert _messages("ALIGN007", "ex:A skos:exactMatch b:B . b:B a skos:Concept .", **base) == []
    # The inverse must use the same predicate.
    assert len(_messages("ALIGN007", "ex:A skos:exactMatch ex:B . ex:B skos:closeMatch ex:A .")) == TWO


# --- ALIGN009 --------------------------------------------------------------------------------


def test_align009_message_confidence_and_scope() -> None:
    found = _run("ALIGN009", "ex:C a owl:Class . a:p a owl:ObjectProperty . ex:C skos:exactMatch a:p .")
    assert [(f.focus, f.message, f.confidence) for f in found] == [
        (
            "https://example.test/onto#C",
            f"skos:exactMatch maps class https://example.test/onto#C to property {A}p.",
            "heuristic",
        )
    ]
    reverse = _run("ALIGN009", "ex:p a owl:ObjectProperty . a:C a owl:Class . ex:p owl:equivalentClass a:C .")
    assert [(f.message, f.confidence) for f in reverse] == [
        (f"owl:equivalentClass maps property https://example.test/onto#p to class {A}C.", "certain")
    ]
    turtle = "ex:C a owl:Class . a:p a owl:ObjectProperty . ex:C skos:exactMatch a:p ."
    assert _messages("ALIGN009", turtle, **OTHER) == []
    assert (
        len(
            _messages(
                "ALIGN009",
                "a:C a owl:Class . ex:p a rdf:Property . a:C skos:exactMatch ex:p .",
                base="https://example.test/",
            )
        )
        == 1
    )
    assert _messages("ALIGN009", "a:C a owl:Class . ex:p a rdf:Property . ex:p skos:exactMatch a:C .") != []
    # A property declared as a class too is a legal pun; so is the reverse.
    pun = "ex:C a owl:Class . a:p a owl:ObjectProperty, owl:Class . ex:C skos:exactMatch a:p ."
    assert _messages("ALIGN009", pun) == []
    pun2 = "ex:C a owl:Class, owl:ObjectProperty . a:p a owl:ObjectProperty . ex:C skos:exactMatch a:p ."
    assert _messages("ALIGN009", pun2) == []
    assert _messages("ALIGN009", "ex:C a owl:Class . ex:C skos:exactMatch ex:C .") == []


# --- ALIGN013 --------------------------------------------------------------------------------


def test_align013_names_the_sorted_predicates() -> None:
    found = _run("ALIGN013", "a:X skos:exactMatch b:Y . b:Y owl:equivalentClass a:X .")
    assert [(f.focus, f.message) for f in found] == [
        (A + "X", f"{A}X and {B}Y are related by several equivalence predicates: owl:equivalentClass, skos:exactMatch.")
    ]


def test_align013_broad_narrow_duplicate_and_scope() -> None:
    found = _run("ALIGN013", "a:X skos:broadMatch b:Y . b:Y skos:narrowMatch a:X .")
    assert [(f.focus, f.message) for f in found] == [
        (A + "X", f"{B}Y being broader than {A}X is asserted by both skos:broadMatch and skos:narrowMatch.")
    ]
    assert _messages("ALIGN013", "a:X skos:broadMatch b:Y . b:Y skos:narrowMatch a:X .", **OTHER) == []
    assert _messages("ALIGN013", "a:X skos:exactMatch b:Y . b:Y owl:sameAs a:X .", **OTHER) == []
    base = {"base": "https://example.test/"}
    for turtle in (
        "ex:X skos:exactMatch b:Y . b:Y owl:sameAs ex:X .",
        "a:X skos:exactMatch ex:Y . ex:Y owl:sameAs a:X .",
        "ex:X skos:broadMatch b:Y . b:Y skos:narrowMatch ex:X .",
        "a:X skos:broadMatch ex:Y . ex:Y skos:narrowMatch a:X .",
    ):
        assert len(_messages("ALIGN013", turtle, **base)) == 1, turtle
    assert _messages("ALIGN013", "a:X skos:broadMatch b:Y . a:X skos:narrowMatch b:Y .") == []
    assert _messages("ALIGN013", "a:X skos:broadMatch b:Y . b:Y skos:broadMatch a:X .") == []


# --- ALIGN014 --------------------------------------------------------------------------------


def test_align014_message_and_orientation() -> None:
    found = _run("ALIGN014", "a:X skos:broadMatch b:Y . b:Y rdfs:subClassOf a:X .")
    assert [(f.focus, f.message) for f in found] == [
        (A + "X", f"skos:broadMatch makes {B}Y broader than {A}X, but the asserted hierarchy places {B}Y below {A}X.")
    ]
    narrow = _run("ALIGN014", "a:X skos:narrowMatch b:Y . a:X rdfs:subClassOf b:Y .")
    assert [(f.focus, f.message) for f in narrow] == [
        (A + "X", f"skos:narrowMatch makes {A}X broader than {B}Y, but the asserted hierarchy places {A}X below {B}Y.")
    ]


def test_align014_scope_cycles_and_deep_chain() -> None:
    turtle = "a:X skos:broadMatch b:Y . b:Y rdfs:subClassOf a:X ."
    assert _messages("ALIGN014", turtle, **OTHER) == []
    base = {"base": "https://example.test/"}
    assert len(_messages("ALIGN014", "ex:X skos:broadMatch b:Y . b:Y rdfs:subClassOf ex:X .", **base)) == 1
    assert len(_messages("ALIGN014", "a:X skos:broadMatch ex:Y . ex:Y rdfs:subClassOf a:X .", **base)) == 1
    assert _messages("ALIGN014", turtle + " a:X rdfs:subClassOf b:Y .") == []
    chain = "\n".join(f"a:n{i + 1} rdfs:subClassOf a:n{i} ." for i in range(300))
    assert len(_messages("ALIGN014", chain + " a:n0 skos:broadMatch a:n300 .")) == 1
    assert _messages("ALIGN014", chain + " a:n300 skos:broadMatch a:n0 .") == []
    diamond = (
        "a:X skos:broadMatch a:T . a:T rdfs:subClassOf a:L, a:R . a:L rdfs:subClassOf a:X . a:R rdfs:subClassOf a:L ."
    )
    assert len(_messages("ALIGN014", diamond)) == 1
    unrelated = (
        "a:X skos:broadMatch a:T . a:T rdfs:subClassOf a:L, a:R . a:L rdfs:subClassOf a:M . a:R rdfs:subClassOf a:M ."
    )
    assert _messages("ALIGN014", unrelated) == []


# --- ALIGN015 --------------------------------------------------------------------------------


def test_align015_lists_every_missing_item_in_order() -> None:
    found = _run("ALIGN015", "ex:M a <https://w3id.org/sssom/MappingSet> .")
    assert [(f.focus, f.message) for f in found] == [
        ("https://example.test/onto#M", "Mapping set has no a version, no a creator, no a licence.")
    ]
    assert _messages(
        "ALIGN015", "ex:M a <http://w3id.org/sssom/MappingSet> ; owl:versionIRI ex:v ; dcterms:license ex:L ."
    ) == ["Mapping set has no a creator."]
    assert _messages(
        "ALIGN015", "ex:M a <https://w3id.org/sssom/MappingSet> ; dcterms:hasVersion '1' ; dcterms:creator 'x' ."
    ) == ["Mapping set has no a licence."]
    assert _messages(
        "ALIGN015", "ex:M a <https://w3id.org/sssom/MappingSet> ; dcterms:creator 'x' ; dcterms:license ex:L ."
    ) == ["Mapping set has no a version."]
    assert _messages("ALIGN015", "[] a <https://w3id.org/sssom/MappingSet> .") == []
