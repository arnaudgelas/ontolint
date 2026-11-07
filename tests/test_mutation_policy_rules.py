"""Exact-expectation tests for the policy-driven rules (policy_rules module)."""

# ruff: noqa: PLR2004

from __future__ import annotations

import re

import pytest
from rdflib import Graph
from rule_harness import graph

from ontolint import Linter
from ontolint.models import Finding
from ontolint.policy import Policy
from ontolint.rules import policy_rules
from ontolint.rules.specs import FIXES, SEVERITY

RULES = ("GOV016", "GOV020", "ALIGN012", "ALIGN016")
COMMENT = "http://www.w3.org/2000/01/rdf-schema#comment"
LABEL = "http://www.w3.org/2000/01/rdf-schema#label"
PREF = "http://www.w3.org/2004/02/skos/core#prefLabel"
NOTE = "https://example.org/vocab#note"


def _run(data: Graph, policy: Policy | None = None, rules: tuple[str, ...] = RULES) -> list[Finding]:
    """Run the module directly (independent of registration) and keep the findings of ``rules``."""
    for spec in policy_rules.SPECS:
        SEVERITY.setdefault(spec.rule_id, spec.severity.value)
        FIXES.setdefault(spec.rule_id, spec.suggestion)
    linter = Linter(data, policy=policy)
    policy_rules.run(linter.rule_context)
    return [f for f in linter.rule_context.findings if f.rule in rules]


def _view(findings: list[Finding]) -> list[tuple[str, str, str]]:
    return sorted((f.rule, f.focus, f.message) for f in findings)


def _required(**kinds: list[str]) -> Policy:
    return Policy.from_mapping({"required_annotations": kinds})


@pytest.mark.parametrize("policy", [None, Policy()])
def test_unset_policy_makes_every_rule_silent(policy: Policy | None) -> None:
    data = graph(
        "ex:A a owl:Class ; skos:exactMatch <https://x.test/A> . ex:p a owl:ObjectProperty . ex:c a skos:Concept ."
        ' ex:i a owl:NamedIndividual ; owl:sameAs <https://x.test/i> . ex:B a owl:Class ; rdfs:label "B" .'
    )
    assert _run(data, policy) == []


def test_gov016_message_lists_sorted_compact_names_once_per_term() -> None:
    data = graph("ex:A a owl:Class .")
    policy = _required(**{"class": [NOTE, LABEL, COMMENT, PREF]})
    found = _run(data, policy, ("GOV016",))
    assert _view(found) == [
        (
            "GOV016",
            "https://example.test/onto#A",
            f"Missing required annotations: {NOTE}, rdfs:comment, rdfs:label, skos:prefLabel.",
        )
    ]


def test_gov016_only_missing_predicates_are_listed() -> None:
    data = graph('ex:A a owl:Class ; rdfs:label "A" ; skos:prefLabel "A"@en .')
    found = _run(data, _required(**{"class": [LABEL, COMMENT, PREF]}), ("GOV016",))
    assert [f.message for f in found] == ["Missing required annotations: rdfs:comment."]


def test_gov016_kinds_are_independent() -> None:
    data = graph(
        "ex:A a owl:Class . ex:p a owl:DatatypeProperty . ex:c a skos:Concept . ex:i a owl:NamedIndividual ."
        " ex:n a owl:Class, owl:NamedIndividual ."
    )
    found = _run(
        data,
        _required(**{"class": [COMMENT], "property": [LABEL], "concept": [PREF], "individual": [NOTE]}),
        ("GOV016",),
    )
    assert _view(found) == [
        ("GOV016", "https://example.test/onto#A", "Missing required annotations: rdfs:comment."),
        ("GOV016", "https://example.test/onto#c", "Missing required annotations: skos:prefLabel."),
        ("GOV016", "https://example.test/onto#i", f"Missing required annotations: {NOTE}."),
        ("GOV016", "https://example.test/onto#n", f"Missing required annotations: {NOTE}, rdfs:comment."),
        ("GOV016", "https://example.test/onto#p", "Missing required annotations: rdfs:label."),
    ]


@pytest.mark.parametrize(
    ("value", "fires"),
    [
        ('"text"', False),
        ('"x"@en', False),
        ("ex:B", False),
        ('" "', True),
        ('""', True),
        ('"\\t\\n"', True),
        ("[]", True),
    ],
)
def test_gov016_value_must_be_non_blank_literal_or_iri(value: str, fires: bool) -> None:
    data = graph(f"ex:A a owl:Class ; rdfs:comment {value} .")
    assert bool(_run(data, _required(**{"class": [COMMENT]}), ("GOV016",))) is fires


def test_gov016_deprecated_terms_are_skipped_only_when_true() -> None:
    data = graph("ex:A a owl:Class ; owl:deprecated true . ex:B a owl:Class ; owl:deprecated false .")
    found = _run(data, _required(**{"class": [COMMENT]}), ("GOV016",))
    assert [f.focus for f in found] == ["https://example.test/onto#B"]


def test_gov016_skips_foreign_terms() -> None:
    data = graph("ex:o a owl:Ontology . ex:A a owl:Class . <https://other.test/Z> a owl:Class .")
    policy = Policy.from_mapping({"base": "https://example.test/onto#", "required_annotations": {"class": [COMMENT]}})
    assert [f.focus for f in _run(data, policy, ("GOV016",))] == ["https://example.test/onto#A"]


def test_gov020_one_warning_per_unknown_key() -> None:
    policy = Policy.from_mapping({"zeta": 1, "alpha": 2, "base": None})
    found = _run(Graph(), policy, ("GOV020",))
    assert _view(found) == [
        ("GOV020", "(policy)", "Unknown policy key 'alpha' is ignored."),
        ("GOV020", "(policy)", "Unknown policy key 'zeta' is ignored."),
    ]
    assert {f.severity for f in found} == {"warning"}


def test_gov020_truncates_long_keys() -> None:
    key = "k" * 81
    (finding,) = _run(Graph(), Policy.from_mapping({key: 1}), ("GOV020",))
    assert finding.message == f"Unknown policy key '{'k' * 80}...' is ignored."
    (exact,) = _run(Graph(), Policy.from_mapping({"k" * 80: 1}), ("GOV020",))
    assert exact.message == f"Unknown policy key '{'k' * 80}' is ignored."


def test_gov020_independent_of_the_graph() -> None:
    assert len(_run(graph("ex:A a owl:Class ."), Policy.from_mapping({"x": 1}), ("GOV020",))) == 1


NS = ("https://ref.test/a#", "https://ref.test/b/")


def test_align012_reports_each_outside_target_with_its_predicate() -> None:
    data = graph(
        "ex:A a owl:Class ; skos:exactMatch <https://nope.test/A>, <https://ref.test/a#A> ;"
        " owl:equivalentClass <https://nope.test/B> .\n"
        "ex:p a owl:ObjectProperty ; owl:equivalentProperty <https://nope.test/p> .\n"
        "ex:i a owl:NamedIndividual ; owl:sameAs <https://nope.test/i> .\n"
        "ex:c a skos:Concept ; skos:broadMatch <https://nope.test/c> ; skos:narrowMatch <https://nope.test/d> ;"
        " skos:relatedMatch <https://nope.test/e> ; skos:closeMatch <https://ref.test/b/c> ."
    )
    found = _run(data, Policy(alignment_namespaces=NS), ("ALIGN012",))
    suffix = "is outside the declared alignment namespaces."
    assert _view(found) == [
        ("ALIGN012", "https://example.test/onto#A", f"owl:equivalentClass target https://nope.test/B {suffix}"),
        ("ALIGN012", "https://example.test/onto#A", f"skos:exactMatch target https://nope.test/A {suffix}"),
        ("ALIGN012", "https://example.test/onto#c", f"skos:broadMatch target https://nope.test/c {suffix}"),
        ("ALIGN012", "https://example.test/onto#c", f"skos:narrowMatch target https://nope.test/d {suffix}"),
        ("ALIGN012", "https://example.test/onto#c", f"skos:relatedMatch target https://nope.test/e {suffix}"),
        ("ALIGN012", "https://example.test/onto#i", f"owl:sameAs target https://nope.test/i {suffix}"),
        ("ALIGN012", "https://example.test/onto#p", f"owl:equivalentProperty target https://nope.test/p {suffix}"),
    ]


def test_align012_prefix_match_is_exact_start() -> None:
    data = graph(
        "ex:A a owl:Class ; skos:exactMatch <https://ref.test/a#X> ; skos:closeMatch <https://ref.test/a> ;"
        " skos:relatedMatch <https://pre.https://ref.test/a#X> ."
    )
    found = _run(data, Policy(alignment_namespaces=("https://ref.test/a#",)), ("ALIGN012",))
    assert sorted(f.message.split()[0] for f in found) == ["skos:closeMatch", "skos:relatedMatch"]


def test_align012_ignores_self_targets_literals_and_other_predicates() -> None:
    data = graph(
        'ex:A a owl:Class ; owl:sameAs ex:A ; skos:exactMatch "lit" ; skos:mappingRelation <https://nope.test/m> ;'
        " rdfs:seeAlso <https://nope.test/s> ."
    )
    assert _run(data, Policy(alignment_namespaces=NS), ("ALIGN012",)) == []


def _coverage(total: int, mapped: int) -> Graph:
    lines = [f"ex:C{i} a owl:Class ." for i in range(total)]
    lines += [f"ex:C{i} owl:equivalentClass <https://r.test/C{i}> ." for i in range(mapped)]
    return graph("\n".join(lines))


@pytest.mark.parametrize(
    ("total", "mapped", "ratio", "fires"),
    [
        (10, 4, 0.5, True),
        (10, 5, 0.5, False),
        (10, 6, 0.5, False),
        (4, 0, 0.5, True),
        (2, 0, 0.5, True),
    ],
)
def test_align016_ratio_boundary_is_strict(total: int, mapped: int, ratio: float, fires: bool) -> None:
    policy = Policy(alignment_min_coverage=ratio, metric_min_sample=2)
    assert bool(_run(_coverage(total, mapped), policy, ("ALIGN016",))) is fires


@pytest.mark.parametrize(("total", "fires"), [(9, False), (10, True), (11, True)])
def test_align016_sample_boundary(total: int, fires: bool) -> None:
    policy = Policy(alignment_min_coverage=0.5)
    assert bool(_run(_coverage(total, 0), policy, ("ALIGN016",))) is fires


def test_align016_message_and_focus() -> None:
    data = graph("ex:o a owl:Ontology . ex:A a owl:Class . ex:B a owl:Class . ex:p a owl:ObjectProperty .")
    data.add(next(iter(graph("ex:A owl:sameAs <https://r.test/A> ."))))
    policy = Policy(alignment_min_coverage=0.5, metric_min_sample=3)
    assert _view(_run(data, policy, ("ALIGN016",))) == [
        ("ALIGN016", "https://example.test/onto#o", "1 of 3 classes and properties have a mapping (0.33 < 0.50).")
    ]


def test_align016_focus_falls_back_without_ontology() -> None:
    (finding,) = _run(_coverage(2, 0), Policy(alignment_min_coverage=1.0, metric_min_sample=2), ("ALIGN016",))
    assert finding.focus == "urn:ontolint:graph"
    assert finding.severity == "info"


def test_align016_counts_distinct_terms_and_ignores_self_and_deprecated() -> None:
    data = graph(
        "ex:A a owl:Class ; skos:exactMatch <https://r.test/1>, <https://r.test/2> ; owl:sameAs ex:A .\n"
        "ex:B a owl:Class ; owl:equivalentClass ex:B .\n"
        "ex:p a owl:ObjectProperty ; owl:equivalentProperty <https://r.test/p> .\n"
        "ex:D a owl:Class ; owl:deprecated true ."
    )
    (finding,) = _run(data, Policy(alignment_min_coverage=0.7, metric_min_sample=3), ("ALIGN016",))
    assert finding.message == "2 of 3 classes and properties have a mapping (0.67 < 0.70)."


def test_align016_message_format_two_decimals() -> None:
    (finding,) = _run(_coverage(10, 1), Policy(alignment_min_coverage=0.5), ("ALIGN016",))
    assert re.fullmatch(r"1 of 10 classes and properties have a mapping \(0\.10 < 0\.50\)\.", finding.message)
