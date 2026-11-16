"""Targeted tests that pin behaviour the mutation run found unobserved (owl_expressions)."""

from __future__ import annotations

from itertools import permutations

from rdflib import BNode, Graph, URIRef
from rdflib.namespace import OWL
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.models import ExecutionStatus, Finding


def _run(rule: str, data: Graph) -> list[Finding]:
    result = Linter(data).execute([rule])
    assert {x.status for x in result.executions} == {ExecutionStatus.EXECUTED}, result.executions
    return list(result.findings)


def test_owl039_message_names_the_cardinality_predicate() -> None:
    g = graph("[] a owl:Restriction ; owl:onProperty ex:p ; owl:minCardinality 0 .")
    assert [f.message for f in _run("OWL039", g)] == ["owl:minCardinality 0 holds for every individual."]


def test_owl040_object_property_rejects_rdfs_datatype_filler() -> None:
    g = graph(
        "ex:p a owl:ObjectProperty . ex:DT a rdfs:Datatype ."
        " [] a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:DT ."
    )
    assert len(_run("OWL040", g)) == 1


def test_owl040_data_property_rejects_restriction_filler() -> None:
    g = graph(
        "ex:p a owl:DatatypeProperty . [] a owl:Restriction ; owl:onProperty ex:p ;"
        " owl:someValuesFrom [ a owl:Restriction ; owl:onProperty ex:q ; owl:hasValue 1 ] ."
    )
    assert len(_run("OWL040", g)) == 1


def test_owl040_data_property_accepts_filler_that_is_also_a_datatype() -> None:
    g = graph(
        "ex:p a owl:DatatypeProperty . ex:X a owl:Class, rdfs:Datatype ."
        " [] a owl:Restriction ; owl:onProperty ex:p ; owl:someValuesFrom ex:X ."
    )
    assert _run("OWL040", g) == []


def _cycle(*edges: tuple[str, str]) -> Graph:
    g = Graph()
    for a, b in edges:
        g.add((URIRef(BASE + a), OWL.complementOf, URIRef(BASE + b)))
    return g


def test_owl041_detects_odd_cycles_of_various_shapes() -> None:
    for n in (3, 5, 7):
        names = [f"c{i}" for i in range(n)]
        g = _cycle(*((names[i], names[(i + 1) % n]) for i in range(n)))
        assert len(_run("OWL041", g)) == 1, n


def _blank_cycle(labels: tuple[str, ...], named: int) -> Graph:
    """An odd ``owl:complementOf`` cycle through ``named`` IRIs and the blank nodes ``labels``, in a fixed shape."""
    nodes = [URIRef(BASE + f"c{i}") for i in range(named)] + [BNode(label) for label in labels]
    g = Graph()
    for i, node in enumerate(nodes):
        g.add((node, OWL.complementOf, nodes[(i + 1) % len(nodes)]))
    return g


def test_owl041_names_the_same_node_whatever_labels_the_blank_nodes_have() -> None:
    """Issue 108: the culprit is chosen by a walk over the nodes, which must not depend on parser-chosen labels."""
    for named, blanks in ((1, 2), (2, 1), (0, 3), (1, 4), (0, 5)):
        # Label pairs from the three schemes of the metamorphic test, in every assignment to the nodes.
        pool = ("b1", "b2", "b3", "b4", "b5", "zz", "yy", "N0", "N1", "x")
        results = set()
        for labels in permutations(pool, blanks):
            (finding,) = _run("OWL041", _blank_cycle(labels, named))
            results.add((finding.focus, finding.message))
        assert len(results) == 1, (named, blanks, results)


def test_owl041_keeps_its_focus_on_a_triangle_of_iris() -> None:
    """Only blank nodes change their place in the walk: a triangle of IRIs is focused as it always was."""
    g = _cycle(("c1", "c2"), ("c2", "c0"), ("c0", "c1"))
    assert [f.focus for f in _run("OWL041", g)] == [BASE + "c2"]
