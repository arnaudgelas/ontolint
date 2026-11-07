"""Mutation-killing tests for hierarchy_quality, the single-child chain walk and list support."""

from __future__ import annotations

import dataclasses
import signal
from collections import defaultdict
from collections.abc import Iterator

import pytest
from rdflib import BNode, URIRef
from rule_harness import BASE, graph

from ontolint import Linter
from ontolint.engine import build_context
from ontolint.policy import Policy
from ontolint.rules import hierarchy_quality as hq
from ontolint.rules.classes import _chain_lengths
from ontolint.rules.support import list_items


def ex(name: str) -> URIRef:
    return URIRef(BASE + name)


def ctx_for(turtle: str):
    return build_context(graph(turtle), None, Policy())


def findings(turtle: str, rule: str) -> list[tuple[str, str]]:
    result = Linter(graph(turtle)).execute([rule])
    return sorted((f.rule, str(f.focus)) for f in result.findings)


@pytest.fixture
def deadline() -> Iterator[None]:
    """Fail fast (instead of hanging) when a mutant makes a walk non-terminating."""

    def boom(signum: int, frame: object) -> None:
        raise TimeoutError("walk did not terminate")

    old = signal.signal(signal.SIGALRM, boom)
    signal.alarm(5)
    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old)


def test_chain_lengths_terminate_on_single_child_cycle(deadline: None) -> None:
    a, b, c = ex("a"), ex("b"), ex("c")
    children = defaultdict(set, {a: {b}, b: {a}, c: {a}})
    lengths = _chain_lengths([a, b, c], children)
    assert lengths == {a: 2, b: 2, c: 3}


def test_hierarchy_is_frozen() -> None:
    h = hq.Hierarchy({}, {})
    with pytest.raises(dataclasses.FrozenInstanceError):
        h.supers = {}  # type: ignore[misc]


def test_is_remainder_false_without_marker() -> None:
    assert hq._is_remainder(("widget",), {"widget"}) is False
    assert hq._is_remainder(("other", "widget"), {"widget"}) is True


def test_disjoint_pairs_are_sorted_for_either_assertion_order() -> None:
    ctx = ctx_for("ex:A a owl:Class . ex:B a owl:Class . ex:B owl:disjointWith ex:A .")
    assert hq._disjoint_pairs(ctx) == {(ex("A"), ex("B"))}
    ctx = ctx_for("ex:A a owl:Class . ex:B a owl:Class . ex:A owl:disjointWith ex:B .")
    assert hq._disjoint_pairs(ctx) == {(ex("A"), ex("B"))}


def test_all_disjoint_classes_yield_each_unordered_pair_once() -> None:
    ctx = ctx_for(
        """ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class .
        [] a owl:AllDisjointClasses ; owl:members ( ex:A ex:B ex:C ) ."""
    )
    assert hq._disjoint_pairs(ctx) == {(ex("A"), ex("B")), (ex("A"), ex("C")), (ex("B"), ex("C"))}


def test_equivalent_ancestors_ignore_non_class_or_self_pairs() -> None:
    turtle = """ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A .
    ex:A owl:equivalentClass ex:A .
    ex:B owl:equivalentClass ex:Undeclared .
    ex:Undeclared rdfs:subClassOf ex:B .
    ex:A owl:equivalentClass [ a owl:Class ] ."""
    assert findings(turtle, "CLS021") == []
    positive = turtle + " ex:A owl:equivalentClass ex:B ."
    assert findings(positive, "CLS021") == [("CLS021", str(ex("B")))]


def test_equivalent_ancestors_bnode_pair_is_skipped() -> None:
    g = graph("ex:A a owl:Class .")
    node = BNode()
    g.add((node, URIRef("http://www.w3.org/2002/07/owl#equivalentClass"), ex("A")))
    assert Linter(g).execute(["CLS021"]).findings == ()


def test_multi_typed_requires_two_declared_classes() -> None:
    ctx = ctx_for(
        """ex:A a owl:Class . ex:B a owl:Class . ex:C a owl:Class .
        ex:one a ex:A .
        ex:two a ex:A, ex:B .
        ex:with_undeclared a ex:A, ex:Missing .
        ex:with_restriction a ex:A, [ a owl:Restriction ] .
        ex:three a ex:A, ex:B, ex:C ."""
    )
    typed = hq._multi_typed(ctx)
    assert typed == {
        ex("two"): frozenset({ex("A"), ex("B")}),
        ex("three"): frozenset({ex("A"), ex("B"), ex("C")}),
    }


def test_multi_typed_excludes_classes_as_subjects() -> None:
    ctx = ctx_for("ex:A a owl:Class . ex:B a owl:Class . ex:A a ex:B . ex:A a ex:A .")
    assert hq._multi_typed(ctx) == {}


def test_redundant_types_with_exactly_two_types() -> None:
    turtle = "ex:A a owl:Class . ex:B a owl:Class ; rdfs:subClassOf ex:A . ex:i a ex:A, ex:B ."
    assert findings(turtle, "CLS025") == [("CLS025", str(ex("i")))]


def test_list_items_limit_boundary() -> None:
    g = graph("ex:l rdf:first ex:a ; rdf:rest [ rdf:first ex:b ; rdf:rest [ rdf:first ex:c ; rdf:rest rdf:nil ] ] .")
    assert list_items(g, ex("l"), limit=3) == [ex("a"), ex("b"), ex("c")]
    assert list_items(g, ex("l"), limit=2) is None
