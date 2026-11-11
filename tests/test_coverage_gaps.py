"""Exact findings for the coverage gaps closed in the OWL, SHACL and SKOS rules (TODO.md, P1 audit item).

Each gap was a stated exclusion: a construct the W3C specification rejects or makes inconsistent that the rule
left silent.  These tests pin the focus, message and subject of each new condition; the rule cases
(``tests/rule_cases``) carry the positive and negative fixtures, and ``test_coverage_gap_stability`` that the
findings reported before stay as they were.  ``ex:`` stands for the cases' base IRI.
"""

from __future__ import annotations

from rule_harness import BASE, graph

from ontolint import Linter

OWL = "http://www.w3.org/2002/07/owl#"

Found = set[tuple[str, str, tuple[str, ...]]]


def short(text: str) -> str:
    return text.replace(BASE, "ex:")


def found(rule: str, turtle: str, shapes: str | None = None) -> Found:
    """``(focus, message, subject)`` of every ``rule`` finding when only ``rule`` runs, ``ex:`` shortened."""
    shapes_graph = graph(shapes) if shapes is not None else None
    findings = Linter(graph(turtle), shapes_graph).execute([rule]).findings
    return {(short(f.focus), short(f.message), tuple(map(short, f.subject))) for f in findings if f.rule == rule}


# --- OWL010: a chain needs two operands (SS 9.2.1, MAP Table 16) --------------------------------------


def test_owl010_reports_an_empty_chain() -> None:
    assert found("OWL010", "ex:p owl:propertyChainAxiom () .") == {
        ("ex:p", "Property-chain axiom list is empty.", ("empty",))
    }


def test_owl010_reports_a_chain_that_is_no_rdf_list() -> None:
    malformed = {("ex:p", "Property-chain axiom does not point to a well-formed RDF list.", ("malformed",))}
    assert found("OWL010", 'ex:p owl:propertyChainAxiom "ex:q" .') == malformed
    assert found("OWL010", "ex:p owl:propertyChainAxiom _:l . _:l rdf:first ex:q .") == malformed
    assert found("OWL010", "ex:p owl:propertyChainAxiom _:l . _:l rdf:first ex:q ; rdf:rest _:l .") == malformed


def test_owl010_tells_each_defective_chain_of_one_property_apart() -> None:
    turtle = "ex:p owl:propertyChainAxiom ( ex:q ), (), ex:r, ( ex:s ex:t ) ."
    assert found("OWL010", turtle) == {
        ("ex:p", "Property-chain axiom has one operand.", ()),
        ("ex:p", "Property-chain axiom list is empty.", ("empty",)),
        ("ex:p", "Property-chain axiom does not point to a well-formed RDF list.", ("malformed",)),
    }
