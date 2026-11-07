"""Targeted tests that pin behaviour the mutation run found unobserved (OWL axiom rules)."""

from __future__ import annotations

from typing import Any

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL, RDFS
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding


def _run(rule: str, data: Graph, **options: Any) -> list[Finding]:
    result = Linter(data, None, **options).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def _ex(name: str) -> URIRef:
    return URIRef(BASE + name)


# --- OWL020 ----------------------------------------------------------------------------------


def test_owl020_two_property_cycle_is_reported_but_a_chain_is_not() -> None:
    cycle = graph("ex:p rdfs:subPropertyOf ex:q . ex:q rdfs:subPropertyOf ex:p .")
    assert [f.rule for f in _run("OWL020", cycle)] == ["OWL020"]
    chain = graph("ex:p rdfs:subPropertyOf ex:q . ex:q rdfs:subPropertyOf ex:r .")
    assert _run("OWL020", chain) == []


def test_owl020_ignores_cycles_through_blank_nodes() -> None:
    data = graph("ex:p rdfs:subPropertyOf [ rdfs:subPropertyOf ex:p ] .")
    blank = next(data.objects(_ex("p"), RDFS.subPropertyOf))
    data.add((_ex("p"), RDFS.subPropertyOf, blank))
    data.add((blank, RDFS.subPropertyOf, _ex("p")))
    assert _run("OWL020", data) == []


# --- OWL021 ----------------------------------------------------------------------------------


def test_owl021_message_names_the_kind_of_each_side() -> None:
    obj = _run("OWL021", graph("ex:p a owl:ObjectProperty ; rdfs:subPropertyOf ex:d . ex:d a owl:DatatypeProperty ."))
    assert [f.message for f in obj] == [
        f"Object property is related by {RDFS.subPropertyOf} to datatype property {_ex('d')}."
    ]
    dat = _run("OWL021", graph("ex:d a owl:DatatypeProperty ; rdfs:subPropertyOf ex:p . ex:p a owl:ObjectProperty ."))
    assert [f.message for f in dat] == [
        f"Datatype property is related by {RDFS.subPropertyOf} to object property {_ex('p')}."
    ]


# --- OWL023 ----------------------------------------------------------------------------------


def test_owl023_self_inverse_and_blank_inverse_do_not_count() -> None:
    data = graph("ex:p owl:inverseOf ex:p , ex:q .")
    assert _run("OWL023", data) == []
    blank = graph("ex:p owl:inverseOf ex:q .")
    blank.add((_ex("p"), OWL.inverseOf, BNode()))
    assert _run("OWL023", blank) == []


# --- OWL024 / OWL025 -------------------------------------------------------------------------


def test_owl025_unrelated_group_members_are_not_reported() -> None:
    data = graph("[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ex:C ) .")
    assert _run("OWL025", data) == []


def test_owl025_group_reports_a_non_adjacent_related_pair() -> None:
    data = graph("[] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ex:C ) . ex:A rdfs:subClassOf ex:C .")
    assert [f.focus for f in _run("OWL025", data)] == [str(_ex("A"))]


# --- OWL029 ----------------------------------------------------------------------------------


def test_owl029_reports_once_on_the_lesser_node() -> None:
    data = graph("ex:p a owl:AsymmetricProperty . ex:a ex:p ex:b . ex:b ex:p ex:a .")
    assert [f.focus for f in _run("OWL029", data)] == [str(_ex("a"))]


def test_owl029_same_text_distinct_nodes_are_not_a_pair() -> None:
    data = graph("ex:p a owl:AsymmetricProperty .")
    uri, blank = _ex("n"), BNode(str(_ex("n")))
    data.add((uri, _ex("p"), blank))
    data.add((blank, _ex("p"), uri))
    assert _run("OWL029", data) == []
