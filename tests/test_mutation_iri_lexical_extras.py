"""Behavioural pins for IRI015, LEX018 and LEX021."""

from __future__ import annotations

import pytest
from rdflib.namespace import RDFS, SKOS
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import Severity
from ontolint.rules import iri_lexical_extras as mod


def _run(turtle: str) -> list[tuple[str, str, str]]:
    linter = Linter(graph(turtle))
    mod.run(linter.rule_context)
    return sorted((f.rule, f.focus, f.message) for f in linter.rule_context.findings)


def test_specs() -> None:
    assert [(s.rule_id, s.family, s.severity, s.category, s.module) for s in mod.SPECS] == [
        ("IRI015", "IRI", Severity.INFO, "heuristic", "iri_lexical_extras"),
        ("LEX018", "LEX", Severity.WARNING, "heuristic", "iri_lexical_extras"),
        ("LEX021", "LEX", Severity.INFO, "heuristic", "iri_lexical_extras"),
    ]


@pytest.mark.parametrize(
    ("name", "opaque"),
    [("123", True), ("12", False), ("T123", True), ("T_123", True), ("T:123", True), ("T-1234", True),
     ("ABCDEFGH123", True), ("ABCDEFGHI123", False), ("1234", True), ("T12", False)],
)  # fmt: skip
def test_opaque_pattern(name: str, opaque: bool) -> None:
    assert bool(mod.OPAQUE_NAME.match(name)) is opaque


@pytest.mark.parametrize(
    ("name", "readable"),
    [("Person", True), ("hasPart", True), ("has_part", True), ("has-part", True), ("BFO", False), ("Ab", False),
     ("Abcd", True), ("Abc", False), ("ABc1", False), ("1abc", False), ("_abc", False), ("ABC", False)],
)  # fmt: skip
def test_readable_pattern(name: str, readable: bool) -> None:
    assert bool(mod.READABLE_NAME.match(name)) is readable


def test_iri015_message_and_focus() -> None:
    found = _run(
        "ex:b a owl:Class . ex:a a owl:Class . ex:c a owl:Class . ex:d a owl:Class . ex:e a owl:Class ."
        " ex:Zeta a owl:Class . ex:Beta a owl:Class . ex:Alpha a owl:Class . ex:Delta a owl:Class ."
        " ex:N003 a owl:Class . ex:N001 a owl:Class . ex:N002 a owl:Class . ex:N004 a owl:Class ."
    )
    assert found == [
        (
            "IRI015",
            BASE,
            "Namespace mixes 4 opaque local names (e.g. N001, N002, N003) and 4 readable ones "
            "(e.g. Alpha, Beta, Delta).",
        )
    ]


def test_iri015_slash_namespace_and_one_each() -> None:
    found = _run("<https://x.test/v/Person> a owl:Class . <https://x.test/v/T001> a owl:Class .")
    assert found == [
        (
            "IRI015",
            "https://x.test/v/",
            "Namespace mixes 1 opaque local names (e.g. T001) and 1 readable ones (e.g. Person).",
        )
    ]


def test_iri015_requires_both_kinds_and_ignores_empty_names() -> None:
    assert _run("ex:Person a owl:Class .") == []
    assert _run("ex:T001 a owl:Class .") == []
    assert _run("<https://x.test/> a owl:Class . ex:T001 a owl:Class .") == []
    assert _run("ex:ab12 a owl:Class . ex:T001 a owl:Class .") == []


def test_iri015_namespaces_are_independent_and_sorted() -> None:
    found = _run(
        "<https://b.test/Person> a owl:Class . <https://b.test/T001> a owl:Class ."
        " <https://a.test/Person> a owl:Class . <https://a.test/T001> a owl:Class ."
        " <https://c.test/Person> a owl:Class . <https://d.test/T001> a owl:Class ."
    )
    assert [focus for _, focus, _ in found] == ["https://a.test/", "https://b.test/"]


def test_namespace_helper() -> None:
    assert mod._namespace("https://x.test/a#B") == "https://x.test/a#"
    assert mod._namespace("https://x.test/a/B") == "https://x.test/a/"


@pytest.mark.parametrize(
    "label",
    ["<b>x</b>", "<br/>", "</i>", "<a href='u'>x</a>", "&amp;", "&#233;", "&#xE9;", "&nbsp;", "a<i>b"],
)
def test_lex018_positive(label: str) -> None:
    found = _run(f'ex:A a owl:Class ; rdfs:label "{label}" .'.replace("\\", "\\\\"))
    assert [(r, f, m) for r, f, m in found] == [
        ("LEX018", BASE + "A", f"Label {label!r} contains markup or a character entity.")
    ]


@pytest.mark.parametrize("label", ["R&D", "a < b", "a > b", "<>", "< b>", "<1>", "&;", "& amp;", "&#;", "&#x;", "x"])
def test_lex018_negative(label: str) -> None:
    assert _run(f'ex:A a owl:Class ; rdfs:label "{label}" .') == []


def test_lex018_each_label_predicate_and_literals_only() -> None:
    for predicate in ("rdfs:label", "skos:prefLabel", "skos:altLabel"):
        assert [r for r, _, _ in _run(f'ex:A a owl:Class ; {predicate} "<b>x</b>" .')] == ["LEX018"]
    assert _run('ex:A a owl:Class ; skos:hiddenLabel "<b>x</b>" ; rdfs:comment "<b>x</b>" .') == []
    assert _run("ex:A a owl:Class ; rdfs:label ex:B .") == []
    assert _run('ex:Undeclared rdfs:label "<b>x</b>" .') == []


def test_lex018_dedup_and_one_finding_per_label() -> None:
    found = _run('ex:A a owl:Class ; rdfs:label "<b>x</b>" ; skos:prefLabel "<b>x</b>", "<i>y</i>" .')
    assert [m for _, _, m in found] == [
        "Label '<b>x</b>' contains markup or a character entity.",
        "Label '<i>y</i>' contains markup or a character entity.",
    ]


def test_lex021_positive_message() -> None:
    found = _run('ex:A a owl:Class ; rdfs:label "Cafe\\u0301" .')
    assert found == [("LEX021", BASE + "A", "Label 'Café' is not Unicode NFC-normalized.")]


def test_lex021_negative_and_predicates() -> None:
    assert _run('ex:A a owl:Class ; rdfs:label "Caf\\u00e9" .') == []
    for predicate in ("rdfs:label", "skos:prefLabel", "skos:altLabel"):
        assert [r for r, _, _ in _run(f'ex:A a owl:Class ; {predicate} "e\\u0301" .')] == ["LEX021"]
    assert _run('ex:A a owl:Class ; skos:hiddenLabel "e\\u0301" ; rdfs:comment "e\\u0301" .') == []
    assert _run("ex:A a owl:Class ; rdfs:label ex:B .") == []


def test_both_lex_rules_on_one_label() -> None:
    found = _run('ex:A a owl:Class ; rdfs:label "<b>e\\u0301</b>" .')
    assert [r for r, _, _ in found] == ["LEX018", "LEX021"]


def test_label_predicates_cover_all_three() -> None:
    assert set(mod.LABEL_PREDICATES) == {RDFS.label, SKOS.prefLabel, SKOS.altLabel}
    assert len("abc") == mod.EXAMPLE_LIMIT
