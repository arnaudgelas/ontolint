"""The LEX family specification (see the ``lexical``, ``lexical_quality``, ``iri_lexical_extras`` and
``annotation_whitespace`` docstrings).

One section per rule: each pins a condition, an exclusion or a known gap of the rule's specification, with
the standard it rests on.  SKOS is the SKOS Reference of 2009-08-18, RDFS the RDF Schema 1.1 Recommendation,
RDF 1.1 Concepts the Recommendation of 2014-02-25 and RFC 4647 the language-tag matching standard.
"""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter
from ontolint.policy import Policy

NS = "https://example.test/onto#"


def _messages(rule: str, turtle: str, *languages: str) -> list[str]:
    policy = Policy(languages=languages) if languages else Policy()
    result = Linter(graph(turtle), policy=policy).execute([rule])
    return sorted(f.message for f in result.findings)


def _foci(rule: str, turtle: str, *languages: str) -> list[str]:
    policy = Policy(languages=languages) if languages else Policy()
    result = Linter(graph(turtle), policy=policy).execute([rule])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


# --- defects fixed by this specification ---------------------------------------------------------------


def test_lex008_a_regional_label_satisfies_the_language_range() -> None:
    # RFC 4647 3.3.1 (basic filtering): the range "en" matches the tag "en-GB"; LEX022 and LEX023 already say so.
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@en-GB .', "en") == []
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@EN-gb .', "en") == []
    # A range does not match a shorter tag, nor a tag that merely starts with the same letters.
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@en .', "en-gb") == ["A"]
    assert _foci("LEX008", 'ex:A a owl:Class ; rdfs:label "A"@eng .', "en") == ["A"]


def test_lex003_counts_one_rdf_literal_once() -> None:
    # RDF 1.1 Concepts 3.3: a simple literal is an xsd:string literal, so "A" and "A"^^xsd:string are one
    # RDF term, and SKOS S14 allows one skos:prefLabel per language tag.
    assert _foci("LEX003", 'ex:A a owl:Class ; rdfs:label "A", "A"^^xsd:string .') == []
    assert _foci("LEX003", 'ex:A a owl:Class ; rdfs:label "A", "B"^^xsd:string .') == ["A"]


def test_lex024_counts_one_rdf_literal_once() -> None:
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "x", "x"^^xsd:string .') == []
    assert _foci("LEX024", 'ex:A a owl:Class ; skos:definition "x", "y"^^xsd:string .') == ["A"]
