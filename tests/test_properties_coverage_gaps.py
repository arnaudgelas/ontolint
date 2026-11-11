"""Properties of the coverage-gap fixes, checked against literal readings of the W3C definitions.

* OWL019: the non-simple properties are those OWL 2 Structural Specification section 11.1 defines, computed
  here over property expressions and their inverses exactly as the specification states the relation ``→``;
  the rule's walk over IRIs must agree on every random property hierarchy, for the characteristics and for
  the cardinality restrictions of SS 11.2.
"""

from __future__ import annotations

import random
import re
from collections.abc import Iterable

import pytest
from hypothesis import given
from hypothesis import strategies as st
from hypothesis_strategies import budget
from rdflib import BNode, Graph, Literal, URIRef
from rdflib.collection import Collection
from rdflib.namespace import OWL, RDF, RDFS
from rdflib.term import Node

from ontolint import Linter

pytestmark = pytest.mark.slow

EX = "https://example.test/onto#"
PROPERTIES = tuple(URIRef(f"{EX}p{i}") for i in range(5))
CHARACTERISTICS = (
    OWL.FunctionalProperty,
    OWL.InverseFunctionalProperty,
    OWL.IrreflexiveProperty,
    OWL.AsymmetricProperty,
)

Expression = tuple[URIRef, bool]  # a property, and whether the expression is its inverse
Axiom = tuple[str, Expression, Expression]


def _expression() -> st.SearchStrategy[Expression]:
    return st.tuples(st.sampled_from(PROPERTIES), st.booleans())


AXIOMS: st.SearchStrategy[Axiom] = st.tuples(
    st.sampled_from(("sub", "equivalent", "inverse", "symmetric", "transitive", "chain2", "chain1")),
    _expression(),
    _expression(),
)
DECLARATIONS = st.lists(st.tuples(st.sampled_from(PROPERTIES), st.sampled_from(CHARACTERISTICS)), max_size=6)


def _term(graph: Graph, expression: Expression) -> Node:
    """The RDF term of an expression: the IRI, or a fresh blank ``[ owl:inverseOf p ]``."""
    iri, inverted = expression
    if not inverted:
        return iri
    node = BNode()
    graph.add((node, OWL.inverseOf, iri))
    return node


def build(axioms: Iterable[Axiom], declarations: Iterable[tuple[URIRef, URIRef]]) -> Graph:
    graph = Graph()
    for kind, first, second in axioms:
        if kind == "inverse":  # InverseObjectProperties is mapped from IRIs only
            graph.add((first[0], OWL.inverseOf, second[0]))
        elif kind in ("sub", "equivalent"):
            predicate = RDFS.subPropertyOf if kind == "sub" else OWL.equivalentProperty
            graph.add((_term(graph, first), predicate, _term(graph, second)))
        elif kind in ("symmetric", "transitive"):
            kind_type = OWL.SymmetricProperty if kind == "symmetric" else OWL.TransitiveProperty
            graph.add((_term(graph, first), RDF.type, kind_type))
        else:
            head = BNode()
            Collection(graph, head, [first[0], second[0]] if kind == "chain2" else [first[0]])
            graph.add((_term(graph, first), OWL.propertyChainAxiom, head))
    for prop, characteristic in declarations:
        graph.add((prop, RDF.type, characteristic))
    return graph


def _inv(expression: Expression) -> Expression:
    return expression[0], not expression[1]


def specified_non_simple(axioms: Iterable[Axiom]) -> set[URIRef]:
    """Properties OPE with a composite OPE' such that OPE' →* OPE, the relation built as SS 11.1 states it."""
    arrows: set[tuple[Expression, Expression]] = set()
    composite: set[Expression] = set()
    for kind, first, second in axioms:
        if kind == "sub":
            arrows.add((first, second))
        elif kind == "equivalent":
            arrows |= {(first, second), (second, first)}
        elif kind == "inverse":
            a, b = (first[0], False), (second[0], False)
            arrows |= {(a, _inv(b)), (_inv(b), a)}
        elif kind == "symmetric":
            arrows.add((first, _inv(first)))
        elif kind in ("transitive", "chain2"):
            composite |= {first, _inv(first)}  # TransitiveObjectProperty(OPE) or of INV(OPE); chains of n > 1
    arrows |= {(_inv(a), _inv(b)) for a, b in arrows}  # with A → B also INV(A) → INV(B)
    reached = set(composite)
    stack = list(composite)
    while stack:
        here = stack.pop()
        for a, b in arrows:
            if a == here and b not in reached:
                reached.add(b)
                stack.append(b)
    return {iri for iri, inverted in reached if not inverted}


@budget(0.5)
@given(st.lists(AXIOMS, max_size=8), DECLARATIONS)
def test_owl019_reports_the_characteristics_of_exactly_the_properties_ss_11_1_makes_non_simple(
    axioms: list[Axiom], declarations: list[tuple[URIRef, URIRef]]
) -> None:
    declarations = [*declarations, *((p, OWL.FunctionalProperty) for p in PROPERTIES)]  # every property judged
    findings = Linter(build(axioms, declarations)).execute(["OWL019"]).findings
    reported = {(URIRef(f.focus), URIRef(f.subject[0])) for f in findings}
    non_simple = specified_non_simple(axioms)
    assert reported == {(p, c) for p, c in declarations if p in non_simple}


@budget(0.3)
@given(st.lists(AXIOMS, max_size=8), DECLARATIONS, st.integers(0, 2**32))
def test_owl019_does_not_depend_on_the_order_of_the_triples(
    axioms: list[Axiom], declarations: list[tuple[URIRef, URIRef]], seed: int
) -> None:
    graph = build(axioms, declarations)
    triples = list(graph)
    random.Random(seed).shuffle(triples)  # noqa: S311 -- a permutation, not a secret
    shuffled = Graph()
    for triple in triples:
        shuffled.add(triple)

    def messages(g: Graph) -> set[tuple[str, str]]:
        return {(f.focus, f.message) for f in Linter(g).execute(["OWL019"]).findings}

    assert messages(shuffled) == messages(graph)


@budget(0.3)
@given(st.lists(AXIOMS, max_size=8), st.lists(_expression(), min_size=1, max_size=4))
def test_owl019_reports_the_restrictions_on_exactly_the_properties_ss_11_1_makes_non_simple(
    axioms: list[Axiom], restricted: list[Expression]
) -> None:
    graph = build(axioms, ())
    for expression in restricted:
        restriction = BNode()
        graph.add((restriction, RDF.type, OWL.Restriction))
        graph.add((restriction, OWL.onProperty, _term(graph, expression)))
        graph.add((restriction, OWL.maxCardinality, Literal(1)))
    messages = [f.message for f in Linter(graph).execute(["OWL019"]).findings]
    on_restrictions = {
        m.group(1).removeprefix("ObjectInverseOf(").removesuffix(")")
        for message in messages
        if (m := re.fullmatch(r"Restriction on non-simple property (\S+) \(.*\) uses owl:maxCardinality\.", message))
    }
    non_simple = {str(iri) for iri in specified_non_simple(axioms)}
    assert on_restrictions == {str(iri) for iri, _inverted in restricted} & non_simple


def test_the_oracle_reads_the_specification_as_intended() -> None:
    p0, p1, p2 = PROPERTIES[:3]
    # p0 ⊑ INV(p1): INV(p0) → p1, and INV(p0) is composite with p0.
    assert specified_non_simple([("transitive", (p0, False), (p0, False)), ("sub", (p0, False), (p1, True))]) == {
        p0,
        p1,
    }
    # Non-simplicity flows upwards only.
    assert specified_non_simple([("transitive", (p1, False), (p1, False)), ("sub", (p0, False), (p1, False))]) == {p1}
    assert specified_non_simple([("chain1", (p2, False), (p2, False))]) == set()
