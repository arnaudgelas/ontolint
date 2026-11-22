"""The SKOS family specification (see the ``skos`` and ``skos_integrity`` docstrings).

One section per rule: each pins a condition, an exclusion or a known gap of the rule's specification, with
the standard it rests on.  SKOS is the SKOS Reference of 2009-08-18 and RDF 1.1 Concepts the Recommendation
of 2014-02-25.  ``test_spec_skos_errors.py`` holds the exact messages of SKOS001, SKOS002 and SKOS009.
"""

from __future__ import annotations

from rule_harness import graph

from ontolint import Linter

NS = "https://example.test/onto#"
SCHEME = "ex:s a skos:ConceptScheme ."


def _foci(rule: str, turtle: str) -> list[str]:
    result = Linter(graph(turtle)).execute([rule])
    return sorted(f.focus.removeprefix(NS) for f in result.findings)


# --- defect fixed by this specification ----------------------------------------------------------------


def test_skos020_counts_one_rdf_literal_once() -> None:
    # RDF 1.1 Concepts 3.3: "1" and "1"^^xsd:string are one RDF term, so two concepts holding them share a notation.
    two = 'ex:a skos:inScheme ex:s ; skos:notation "1" . ex:b skos:inScheme ex:s ; skos:notation "1"^^xsd:string .'
    typed = "a skos:Concept ;"
    both = two.replace("ex:a ", f"ex:a {typed} ").replace("ex:b ", f"ex:b {typed} ")
    assert _foci("SKOS020", both) == ["a", "b"]
    # Another datatype is another term.
    assert _foci("SKOS020", both.replace("xsd:string", "xsd:token")) == []
